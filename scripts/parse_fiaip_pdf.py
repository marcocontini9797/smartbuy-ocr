"""Extract the zone price tables of the FIAIP Bologna city report into JSON.

The report ("Osservatorio immobiliare - Prezzi e tendenze", free PDFs on
fiaipemiliaromagna.it/bologna) has one page of tables per zone. Values are
assigned to their column by x position, so "N.D." cells stay empty.

Usage (needs pypdf, not a runtime dependency):
    python scripts/parse_fiaip_pdf.py data/ref/fiaip_bologna_2024.pdf reference/fiaip_bologna_2024.json
"""

from __future__ import annotations

import json
import re
import sys

from pypdf import PdfReader

# Column centres (PDF points) of the four tables of a zone page.
TABLES = [
    {"abitazioni_nuovo": 100, "abitazioni_ristrutturato": 188, "abitazioni_buono": 276, "abitazioni_da_ristrutturare": 364},
    {"uffici_nuovo": 105, "uffici_buono": 186, "negozi_elevato_interesse": 276, "negozi_scarso_interesse": 363},
    {"box_entro_5m": 95, "box_oltre_5m": 161, "box_doppio": 230, "posto_auto_scoperto": 306, "posto_auto_coperto": 372},
    {"affitto_mono_bilocale": 86, "affitto_3_4_vani": 123, "affitto_5_vani": 165, "affitto_uffici_nuovo": 219,
     "affitto_uffici_buono": 254, "affitto_negozi_elevato": 290, "affitto_negozi_scarso": 325,
     "affitto_box_entro_5m": 360, "affitto_box_oltre_5m": 396},
]
UNITS = ["eur_m2", "eur_m2", "eur_corpo", None]
# Rents: homes and garages per month, offices and shops per m² per year.
RENT_UNIT = {"affitto_uffici": "eur_m2_anno", "affitto_negozi": "eur_m2_anno"}


def _items(page) -> list[tuple[float, float, str]]:
    out = []

    def visit(text, cm, tm, font, size):
        text = text.strip()
        if text:
            out.append((tm[4] * cm[0] + cm[4], tm[5] * cm[3] + cm[5], text))

    page.extract_text(visitor_text=visit)
    return out


def _unit(item: str, table: int) -> str:
    if UNITS[table]:
        return UNITS[table]
    return next((unit for prefix, unit in RENT_UNIT.items() if item.startswith(prefix)), "eur_mese")


def parse(path: str) -> list[dict]:
    zones = []
    for index, page in enumerate(PdfReader(path).pages):
        text = page.extract_text() or ""
        head = re.search(r"\n\s*\d+\s*\n(.*?)(?:LOCAZIONI|ABITAZIONI)", text, re.S)
        if "COMPRAVENDITE" not in text or "LOCAZIONI" not in text or "MIN." not in text or not head:
            continue  # map pages and adverts
        header = re.sub(r"([A-Z])(\d)", r"\1 \2", re.sub(r"(?i)bologna", "", re.sub(r"\s+", " ", head.group(1)))).strip()
        codes = re.findall(r"(\d{1,2}[ab]?)(?=\s|$)", header)
        name = re.sub(r"\s+", " ", re.sub(r"\d{1,2}[ab]?(?=\s|$)", "", header)).strip(" -")
        things = _items(page)
        labels = sorted([(y, s) for x, y, s in things if s in ("MIN.", "MAX") and x < 60], key=lambda a: -a[0])
        if len(labels) != 8 or not codes:
            raise ValueError(f"page {index + 1}: unexpected layout ({header!r})")
        values: dict[str, dict] = {}
        for number, table in enumerate(TABLES):
            for bound, (label_y, _) in zip(("min", "max"), labels[2 * number: 2 * number + 2]):
                for x, y, s in things:
                    if x < 60 or abs(y - (label_y - 2.5)) > 3 or not re.fullmatch(r"\d{1,3}(?:\.\d{3})*", s):
                        continue
                    item = min(table, key=lambda key: abs(table[key] - x))
                    if abs(table[item] - x) > 12:
                        raise ValueError(f"page {index + 1}: value {s} far from any column")
                    values.setdefault(item, {"unit": _unit(item, number)})[bound] = int(s.replace(".", ""))
        zones.append({"page": index + 1, "code": "/".join(codes), "name": name, "values": values})
    return zones


if __name__ == "__main__":
    result = parse(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=1)
    print(f"{len(result)} zone")
