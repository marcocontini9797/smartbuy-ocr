"""Small deterministic services shared by the operational API adapters."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.operational_models import CrossValidationFinding, stable_id


APE_REGISTRY = {
    "ER": {"name": "SACE Emilia-Romagna", "region": "Emilia-Romagna", "mode": "official_portal"},
    "LOM": {"name": "CENED Lombardia", "region": "Lombardia", "mode": "official_portal"},
}
PROVINCE_REGION = {"BO": "ER", "MO": "ER", "RE": "ER", "PR": "ER", "FE": "ER", "RA": "ER", "FC": "ER", "RN": "ER", "PC": "ER",
                   "MI": "LOM", "BG": "LOM", "BS": "LOM", "CO": "LOM", "CR": "LOM", "LC": "LOM", "LO": "LOM", "MN": "LOM", "MB": "LOM", "PV": "LOM", "SO": "LOM", "VA": "LOM"}


def route_ape_source(*, province: str | None = None, region_code: str | None = None) -> dict[str, Any]:
    code = (region_code or PROVINCE_REGION.get((province or "").strip().upper()) or "").upper()
    source = APE_REGISTRY.get(code)
    if source:
        return {**source, "region_code": code, "supported": True, "automatic": False,
                "note": "Use the regional official registry; record CAPTCHA or credential constraints explicitly."}
    return {"name": "Regional APE registry adapter required", "region_code": code or None,
            "supported": False, "automatic": False,
            "note": "No regional adapter configured. Verify the seller document and keep official verification pending."}


def validate_gis(*, latitude: float | None, longitude: float | None, expected_city: str | None) -> dict[str, Any]:
    if latitude is None or longitude is None:
        return {"status": "insufficient_evidence", "expected_city": expected_city,
                "reason": "Coordinates are required for municipality validation"}
    valid = -90 <= latitude <= 90 and -180 <= longitude <= 180
    return {"status": "coordinates_valid" if valid else "invalid_coordinates",
            "latitude": latitude, "longitude": longitude, "expected_city": expected_city,
            "requires_authoritative_boundary_check": valid}


def cross_validate_facts(property_id: int, facts: list[dict[str, Any]]) -> list[CrossValidationFinding]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        field = str(fact.get("fact_name") or fact.get("field") or "").strip()
        if field:
            grouped[field].append(fact)
    findings: list[CrossValidationFinding] = []
    for field, rows in grouped.items():
        values = []
        normalized = set()
        evidence_ids = []
        for row in rows:
            raw = row.get("fact_value", row.get("value"))
            value = raw.get("value") if isinstance(raw, dict) and "value" in raw else raw
            source = row.get("source_type") or row.get("source") or "unknown"
            values.append({"value": value, "source": source, "fact_id": row.get("id")})
            if value is not None:
                normalized.add(str(value).strip().casefold())
            evidence_ids.extend(str(item) for item in (row.get("evidence_ids") or []))
        distinct_sources = {str(item["source"]) for item in values if item["source"] != "unknown"}
        if len(normalized) > 1:
            status, action = "conflict", "Verificare le fonti e confermare il valore corretto"
        elif len(normalized) == 1 and len(distinct_sources) >= 2:
            status, action = "consistent", None
        else:
            status, action = "insufficient_evidence", "Acquisire una seconda fonte indipendente"
        findings.append(CrossValidationFinding(
            finding_id=stable_id("cross-validation", property_id, field, *sorted(normalized)),
            property_id=property_id, field=field, status=status, values=values,
            evidence_ids=sorted(set(evidence_ids)), recommended_action=action,
        ))
    return findings

