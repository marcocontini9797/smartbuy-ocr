"""Download and load public market data into Supabase (service role).

- Agenzia delle Entrate, OMI "Volumi di compravendita": quarterly NTN per
  province (capital / rest of province), residential and non-residential.
- Istat, "Elenco comuni italiani": province and provincial-capital flag.
- Protezione Civile: seismic zone of every municipality.
- ISPRA IdroGEO: landslide and flood hazard/risk indicators per municipality
  (the hazard at the exact address is queried live, see document_engine/hazards.py).
- MEF: IRPEF incomes per municipality (2019, 2024) and per postcode (2024).
- Istat: house price index (IPAB), quarterly, by macro-area and large cities.
- FIAIP Bologna: zone price lists, from reference/fiaip_*.json (see parse_fiaip_pdf.py).

Usage: python scripts/load_market_data.py   (re-run when AdE publishes new data)
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.supabase.client import supabase  # noqa: E402

NTN_PAGE = "https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/banche-dati/volumi-di-compravendita"
ISTAT_COMUNI = "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv"
ARCHIVES = ("RESIDENZIALE_DEFINITIVO_2011_2024", "RESIDENZIALE_2025_2026_PROVV",
            "NON_RESIDENZIALE_DEFINITIVO_2011_2024", "NON_RESIDENZIALE_2025_2026_PROVV")
SIZE_CLASSES = {"<= 50": "0_50", "50 -| 85": "50_85", "85 -| 115": "85_115", "115 -| 145": "115_145", "> 145": "145_plus"}


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as response:
        return response.read()


def number(text: str) -> float | None:
    text = text.strip()
    return float(text.replace(".", "").replace(",", ".")) if text else None


def parse_volumes(name: str, content: str, rows: dict) -> None:
    """Merge one AdE CSV into rows keyed by (provincia, capoluogo, series)."""
    series_base = name.removesuffix("_SUP").removesuffix("_CLASSI")
    reader = csv.reader(io.StringIO(content), delimiter=";")
    header = next(reader)
    for record in reader:
        if len(record) < 5 or not record[2].strip():
            continue
        area, regione, provincia, cap = (value.strip() for value in record[:4])
        for column, raw in zip(header[4:], record[4:]):
            value = number(raw)
            column = column.strip()
            if value is None or not column:
                continue
            series = series_base
            for label, code in SIZE_CLASSES.items():
                if column.startswith(label + "_"):
                    series, column = f"{series_base}_{code}", column[len(label) + 1:]
                    break
            match = re.match(r"(\d{4}_\d)(_PROVV)?(_NTN|_SUP_NORM)?$", column)
            if not match:
                raise ValueError(f"{name}: colonna non riconosciuta {column!r}")
            period, provisional, measure = match.groups()
            kind = "surface" if measure == "_SUP_NORM" else "ntn_provisional" if provisional else "ntn"
            row = rows.setdefault((provincia, cap == "cap", series), {
                "provincia": provincia, "capoluogo": cap == "cap", "series": series, "area": area, "regione": regione,
                "ntn": {}, "ntn_provisional": {}, "surface": {}, "source": "Agenzia delle Entrate - OMI, volumi di compravendita"})
            row[kind][period] = value


def load_volumes() -> int:
    page = fetch(NTN_PAGE).decode("utf-8", "replace")
    rows: dict = {}
    for archive in ARCHIVES:
        link = re.search(rf'href="([^"]*/{archive}\.zip[^"]*)"', page)
        if not link:
            raise RuntimeError(f"Archivio {archive} non trovato sulla pagina AdE: il sito potrebbe essere cambiato")
        with zipfile.ZipFile(io.BytesIO(fetch(link.group(1).replace("&amp;", "&")))) as bundle:
            for member in bundle.namelist():
                if member.lower().endswith(".csv"):
                    parse_volumes(Path(member).stem, bundle.read(member).decode("latin-1"), rows)
    payload = list(rows.values())
    for start in range(0, len(payload), 200):
        supabase.table("market_volumes").upsert(payload[start:start + 200]).execute()
    return len(payload)


def load_comuni() -> int:
    reader = csv.reader(io.StringIO(fetch(ISTAT_COMUNI).decode("latin-1")), delimiter=";")
    header = [column.replace("\n", " ").strip() for column in next(reader)]
    col = {name: header.index(name) for name in header}
    capital = next(i for name, i in col.items() if name.startswith("Flag Comune capoluogo"))
    cadastral = next(i for name, i in col.items() if name.startswith("Codice Catastale"))
    istat = next(i for name, i in col.items() if name.startswith("Codice Comune formato alfanumerico"))
    rows = [{"codice_catastale": r[cadastral].strip(), "codice_istat": r[istat].strip(),
             "nome": r[col["Denominazione in italiano"]].strip(), "sigla_provincia": r[col["Sigla automobilistica"]].strip(),
             "regione": r[col["Denominazione Regione"]].strip(), "capoluogo": r[capital].strip() == "1"}
            for r in reader if len(r) > cadastral and r[cadastral].strip()]
    for start in range(0, len(rows), 500):
        supabase.table("istat_comuni").upsert(rows[start:start + 500]).execute()
    return len(rows)


SEISMIC_CSV = ("https://rischi.protezionecivile.it/static/4717c6a369cdc298b69730c9d740e39a/"
               "classificazione-sismica-aggiornata-maggio-2025.csv")
ISPRA_COMUNI = "https://idrogeo.isprambiente.it/api/pir/comuni/export?outputFormat=csv"
MEF_IRPEF = ("https://www1.finanze.gov.it/finanze/analisi_stat/public/v_4_0_0/contenuti/"
             "Redditi_e_principali_variabili_IRPEF_su_base_{kind}_CSV_{year}.zip")
IRPEF_YEARS = {"comunale": (2019, 2024), "subcomunale": (2024,)}
ISTAT_IPAB = "https://esploradati.istat.it/SDMXWS/rest/data/IT1,143_497,1.0/Q..105..?startPeriod=2010"


def upsert(table: str, rows: list[dict], chunk: int = 500) -> int:
    for start in range(0, len(rows), chunk):
        supabase.table(table).upsert(rows[start:start + chunk]).execute()
    return len(rows)


def decimal(text: str | None) -> float | None:
    text = (text or "").strip()
    return float(text) if text not in ("", "NA", "null") else None


def load_seismic() -> int:
    reader = csv.DictReader(io.StringIO(fetch(SEISMIC_CSV).decode("utf-8-sig")), delimiter=";")
    rows = {}
    for r in reader:
        code = (r.get("COD_ISTAT_COMUNE") or "").strip()
        if code and (r.get("ZONA_SISMICA") or "").strip():
            rows[code.zfill(6)] = {"codice_istat": code.zfill(6), "comune": r["COMUNE"].strip(),
                                   "sigla_provincia": (r.get("SIGLA_PROV") or "").strip(), "zona": r["ZONA_SISMICA"].strip()}
    return upsert("seismic_zones", list(rows.values()))


ISPRA_FIELDS = {"flood_area_p3_pct": "aridp3_p", "flood_area_p2_pct": "aridp2_p", "flood_area_p1_pct": "aridp1_p",
                "flood_pop_p3_pct": "popidp3_p", "flood_pop_p2_pct": "popidp2_p",
                "flood_buildings_p3_pct": "edidp3_p", "flood_buildings_p2_pct": "edidp2_p",
                "landslide_area_p4_pct": "ar_frp4_p", "landslide_area_p3_pct": "ar_frp3_p", "landslide_area_p2_pct": "ar_frp2_p",
                "landslide_area_p1_pct": "ar_frp1_p", "landslide_area_aa_pct": "ar_fraa_p",
                "landslide_pop_p3p4_pct": "popfrp3p4p", "landslide_buildings_p3p4_pct": "edfrp3p4p"}


def load_municipal_hazard() -> int:
    reader = csv.DictReader(io.StringIO(fetch(ISPRA_COMUNI).decode("utf-8-sig")))
    rows = []
    for r in reader:
        if not (r.get("pro_com") or "").strip():
            continue
        population = decimal(r.get("pop_res021"))
        rows.append({"codice_istat": r["pro_com"].strip().zfill(6), "comune": r["comune"].strip(),
                     "area_kmq": decimal(r.get("ar_kmq")), "popolazione_2021": int(population) if population is not None else None,
                     **{field: decimal(r.get(column)) for field, column in ISPRA_FIELDS.items()}})
    return upsert("municipal_hazard", rows)


def load_irpef() -> int:
    total = 0
    for kind, years in IRPEF_YEARS.items():
        for year in years:
            with zipfile.ZipFile(io.BytesIO(fetch(MEF_IRPEF.format(kind=kind, year=year)))) as bundle:
                member = next(m for m in bundle.namelist() if m.lower().endswith(".csv"))
                reader = csv.DictReader(io.StringIO(bundle.read(member).decode("latin-1")), delimiter=";")
                rows = {}
                for r in reader:
                    value = lambda name: number(r.get(name) or "")  # noqa: E731
                    taxable, taxable_n = value("Reddito imponibile - Ammontare in euro"), value("Reddito imponibile - Frequenza")
                    key = (year, r["Codice catastale"].strip(), (r.get("CAP") or "").strip())
                    rows[key] = {"anno": year, "codice_catastale": key[1], "cap": key[2], "comune": r["Denominazione Comune"].strip(),
                                 "contribuenti": int(value("Numero contribuenti") or 0),
                                 "reddito_imponibile_eur": taxable,
                                 "reddito_imponibile_medio_eur": round(taxable / taxable_n) if taxable and taxable_n else None,
                                 "reddito_complessivo_freq": int(value("Reddito complessivo - Frequenza") or 0),
                                 "reddito_complessivo_eur": value("Reddito complessivo - Ammontare in euro"),
                                 "reddito_fabbricati_freq": int(value("Reddito da fabbricati - Frequenza") or 0),
                                 "reddito_fabbricati_eur": value("Reddito da fabbricati - Ammontare in euro")}
                total += upsert("irpef_incomes", list(rows.values()))
    return total


def load_house_price_index() -> int:
    """Quarterly IPAB, base 2025=100: index (MEASURE 4), q/q (6) and y/y (7) changes."""
    request = Request(ISTAT_IPAB, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.sdmx.data+csv;version=1.0.0"})
    with urlopen(request, timeout=180) as response:
        reader = csv.DictReader(io.StringIO(response.read().decode("utf-8-sig")))
    rows: dict = {}
    field = {"4": "index_2025", "6": "qoq_pct", "7": "yoy_pct"}
    for r in reader:
        if r["DATA_TYPE"] != "105" or r["MEASURE"] not in field or not r["OBS_VALUE"]:
            continue
        key = (r["REF_AREA"], r["PURCHASES_DWELLINGS"], r["TIME_PERIOD"])
        row = rows.setdefault(key, {"ref_area": key[0], "purchase": key[1], "period": key[2], "index_2025": None,
                                    "qoq_pct": None, "yoy_pct": None, "provisional": False})
        row[field[r["MEASURE"]]] = float(r["OBS_VALUE"])
        row["provisional"] = row["provisional"] or r.get("OBS_STATUS") == "p"
    return upsert("house_price_index", list(rows.values()))


REFERENCE_DIR = Path(__file__).resolve().parents[1] / "reference"
# FIAIP files: reference/fiaip_<comune>_<year>.json, made by scripts/parse_fiaip_pdf.py.
FIAIP_COMUNI = {"bologna": "A944"}


def load_reference_prices() -> int:
    rows = []
    for path in sorted(REFERENCE_DIR.glob("fiaip_*_*.json")):
        _, comune, year = path.stem.split("_")
        for zone in json.loads(path.read_text(encoding="utf-8")):
            for item, value in zone["values"].items():
                rows.append({"source": "FIAIP", "year": int(year), "comune_cat": FIAIP_COMUNI[comune], "zone_code": zone["code"],
                             "zone_name": zone["name"], "item": item, "min_value": value.get("min"),
                             "max_value": value.get("max"), "unit": value["unit"]})
    return upsert("reference_prices", rows)


if __name__ == "__main__":
    print(f"Comuni Istat caricati: {load_comuni()}")
    print(f"Serie di volumi caricate: {load_volumes()}")
    print(f"Classificazione sismica: {load_seismic()} comuni")
    print(f"Pericolosità ISPRA per comune: {load_municipal_hazard()} comuni")
    print(f"Redditi IRPEF: {load_irpef()} righe")
    print(f"Indice prezzi abitazioni Istat: {load_house_price_index()} righe")
    print(f"Listini di zona (FIAIP): {load_reference_prices()} valori")
