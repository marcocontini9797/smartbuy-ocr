"""Download and load public market data into Supabase (service role).

- Agenzia delle Entrate, OMI "Volumi di compravendita": quarterly NTN per
  province (capital / rest of province), residential and non-residential.
- Istat, "Elenco comuni italiani": province and provincial-capital flag.

Usage: python scripts/load_market_data.py   (re-run when AdE publishes new data)
"""

from __future__ import annotations

import csv
import io
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


if __name__ == "__main__":
    print(f"Comuni Istat caricati: {load_comuni()}")
    print(f"Serie di volumi caricate: {load_volumes()}")
