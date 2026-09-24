"""Address to coordinates with OpenStreetMap Nominatim, only if the municipality matches.

A free-text search can return a street with the same name in a nearby town
("Via Rizzoli, Bologna" -> Granarolo dell'Emilia): the result is accepted only
when the municipality it belongs to is the property's city.
"""

from __future__ import annotations

import httpx

from document_engine.cross_validation import norm_comune

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "SmartBuy-Property-Analyzer/1.0"
_MUNICIPALITY_KEYS = ("city", "town", "village", "municipality", "hamlet")


def _municipality(result: dict) -> str | None:
    address = result.get("address") or {}
    return next((address[key] for key in _MUNICIPALITY_KEYS if address.get(key)), None)


def same_municipality(a: str | None, b: str | None) -> bool:
    return bool(a and b) and norm_comune(a) == norm_comune(b)


def geocode(address: str | None, city: str | None,
            bbox: list[float] | None = None) -> tuple[float, float] | None:
    """bbox = [min_lon, min_lat, max_lon, max_lat] of the municipality (from OMI zones).

    Searching inside the municipality box finds the street of that town; the
    municipality check then rejects results from neighbouring towns in the box.
    """
    if not address or not city:
        return None
    attempts = []
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        attempts.append({"q": address, "viewbox": f"{min_lon},{max_lat},{max_lon},{min_lat}", "bounded": 1})
    attempts += [{"street": address, "city": city, "country": "Italia"}, {"q": f"{address}, {city}, Italia"}]
    for params in attempts:
        try:
            response = httpx.get(NOMINATIM_URL, params={**params, "format": "jsonv2", "limit": 5, "countrycodes": "it",
                                                        "addressdetails": 1},
                                 headers={"User-Agent": USER_AGENT, "Accept-Language": "it"}, timeout=10)
            response.raise_for_status()
            results = response.json()
        except Exception:
            continue
        for result in results:
            if same_municipality(_municipality(result), city):
                return float(result["lat"]), float(result["lon"])
    return None


def postcode(lat: float, lon: float) -> str | None:
    """Postcode (CAP) at a position, from Nominatim reverse geocoding."""
    try:
        response = httpx.get("https://nominatim.openstreetmap.org/reverse",
                             params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 1},
                             headers={"User-Agent": USER_AGENT, "Accept-Language": "it"}, timeout=10)
        response.raise_for_status()
        value = (response.json().get("address") or {}).get("postcode")
    except Exception:
        return None
    return value if value and len(value) == 5 and value.isdigit() else None
