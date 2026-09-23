"""Small deterministic services shared by the operational API adapters."""

from __future__ import annotations

from typing import Any

from core.operational_models import CrossValidationFinding
from document_engine.cross_validation import cross_validate


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
    """Backward-compatible entry point: facts only. See ``document_engine.cross_validation``."""
    return cross_validate(property_id, facts=facts)
