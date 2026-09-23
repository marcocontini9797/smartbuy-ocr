"""Measure extraction accuracy on reference documents with known correct values.

For every gold/<name>.<pdf|png|jpg> with a gold/<name>.json, run the real
pipeline (OCR, classification, extraction, verification, second reading) and
compare each expected field with the cross-validation normalizers.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from document_engine.cross_validation import COMPATIBLE, EQUAL, SPECS, _claim, _expand, norm_text, parse_date

ROOT = Path(__file__).parent
GOLD = ROOT / "gold"
REPORTS = ROOT / "reports"
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _normalized(name: str, value) -> dict[str, object]:
    """{comparable_key: normalized value} for one top-level field."""
    out: dict[str, object] = {}
    for canonical, raw in _expand(name, value):
        claim = _claim(canonical, raw, source_key="-", source_label="-")
        if claim:
            out[canonical] = claim.normalized
    if not out and value not in (None, "", [], {}):
        # Fields without a domain comparator: dates, free text.
        date = parse_date(value) if isinstance(value, str) else None
        out[name] = date or norm_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
    return out


def compare(expected: dict, extracted: dict) -> list[dict]:
    rows = []
    for name, expected_value in expected.items():
        want = _normalized(name, expected_value)
        got = _normalized(name, (extracted or {}).get(name))
        for key, want_value in want.items():
            got_value = got.get(key)
            if got_value is None:
                ok, note = False, "mancante"
            elif key in SPECS:
                verdict = SPECS[key].compare(want_value, got_value)[0]
                ok, note = verdict in (EQUAL, COMPATIBLE), verdict
            else:
                ok = want_value == got_value
                note = "uguale" if ok else "diverso"
            rows.append({"field": key, "expected": str(want_value),
                         "extracted": None if got_value is None else str(got_value), "correct": ok, "note": note})
    return rows


async def run_document(path: Path) -> dict:
    from fastapi import UploadFile
    from starlette.datastructures import Headers
    from api_server import ingest_document

    upload = UploadFile(file=io.BytesIO(path.read_bytes()), filename=path.name,
                        headers=Headers({"content-type": MEDIA[path.suffix.lower()]}))
    response = await ingest_document(file=upload, fascicolo_id="evaluation", agente_id="evaluation")
    return json.loads(response.body)


async def main() -> int:
    cases = [p for p in sorted(GOLD.iterdir()) if p.suffix.lower() in MEDIA and p.with_suffix(".json").exists()]
    if not cases:
        print(f"Nessun documento di riferimento in {GOLD}")
        return 1
    results, per_field = [], defaultdict(lambda: [0, 0])
    for path in cases:
        gold = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        print(f"-> {path.name} ...", flush=True)
        payload = await run_document(path)
        rows = compare(gold["expected"], payload.get("extracted_fields") or {})
        type_ok = payload.get("document_type") == gold.get("document_type")
        for row in rows:
            per_field[row["field"]][0] += row["correct"]
            per_field[row["field"]][1] += 1
        correct = sum(row["correct"] for row in rows)
        disagreements = list((payload.get("extraction_disagreements") or {}).keys())
        print(f"   tipo {'OK' if type_ok else 'ERRATO'} ({payload.get('document_type')}) · campi corretti {correct}/{len(rows)}"
              f" · letture discordanti: {disagreements or 'nessuna'}")
        for row in rows:
            if not row["correct"]:
                print(f"     x {row['field']}: atteso {row['expected']!r}, estratto {row['extracted']!r} ({row['note']})")
        results.append({"file": path.name, "type_correct": type_ok, "document_type": payload.get("document_type"),
                        "confidence": payload.get("extraction_confidence"), "fields": rows, "disagreements": disagreements})

    total = sum(n for _, n in per_field.values())
    correct = sum(ok for ok, _ in per_field.values())
    types = sum(r["type_correct"] for r in results)
    print(f"\nPrecisione campi: {correct}/{total} = {correct / total:.1%} · tipo documento corretto: {types}/{len(results)}")
    for field, (ok, n) in sorted(per_field.items(), key=lambda kv: kv[1][0] / kv[1][1]):
        print(f"   {field:32} {ok}/{n}")
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"report-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"field_accuracy": correct / total, "type_accuracy": types / len(results),
                               "per_field": per_field, "documents": results}, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
