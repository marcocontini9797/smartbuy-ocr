"""Distance to nearby amenities (school, transit, supermarket, pharmacy,
park) from a position, via the free OpenStreetMap Overpass API — no key,
no cost, no terms-of-service issue (open data). Used to enrich the
pre-mandate seller-lead estimate with a location factor that OMI zone
quotations alone do not capture.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

# Tried in order: the official instance first, then public mirrors, since any
# one of them can be temporarily down, overloaded, or (as found in testing)
# unreachable from a specific network — never depend on a single instance.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
USER_AGENT = "SmartBuy-Property-Analyzer/1.0"
RADIUS_M = 1500

# category label -> Overpass tag filter(s), each tried in the same query
_CATEGORIES: dict[str, tuple[str, ...]] = {
    "scuola": ('node["amenity"="school"]',),
    "farmacia": ('node["amenity"="pharmacy"]',),
    "supermercato": ('node["shop"="supermarket"]',),
    "trasporto_pubblico": ('node["highway"="bus_stop"]', 'node["railway"~"station|tram_stop"]'),
    "parco": ('node["leisure"="park"]',),
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _query(lat: float, lon: float) -> str:
    clauses = []
    for filters in _CATEGORIES.values():
        for f in filters:
            clauses.append(f"{f}(around:{RADIUS_M},{lat},{lon});")
    return f"[out:json][timeout:10];({''.join(clauses)});out body;"


def nearby_amenities(lat: float, lon: float) -> dict[str, Any] | None:
    """Nearest distance (metres) to each amenity category within RADIUS_M,
    or None for a category with nothing found. Returns None entirely if the
    Overpass API is unreachable or times out — never raises, same as every
    other public-data lookup in this pipeline."""
    elements: list[dict[str, Any]] | None = None
    query = _query(lat, lon)
    for url in OVERPASS_URLS:
        try:
            response = httpx.post(url, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=15)
            response.raise_for_status()
            elements = response.json().get("elements") or []
            break
        except Exception:
            continue
    if elements is None:
        return None

    # Overpass doesn't tag which of our clauses matched, so re-derive the
    # category from the element's own tags.
    def category_of(tags: dict[str, str]) -> str | None:
        if tags.get("amenity") == "school":
            return "scuola"
        if tags.get("amenity") == "pharmacy":
            return "farmacia"
        if tags.get("shop") == "supermarket":
            return "supermercato"
        if tags.get("highway") == "bus_stop" or tags.get("railway") in {"station", "tram_stop"}:
            return "trasporto_pubblico"
        if tags.get("leisure") == "park":
            return "parco"
        return None

    nearest: dict[str, float] = {}
    for element in elements:
        tags = element.get("tags") or {}
        category = category_of(tags)
        if not category or element.get("lat") is None or element.get("lon") is None:
            continue
        distance = _haversine_m(lat, lon, element["lat"], element["lon"])
        if category not in nearest or distance < nearest[category]:
            nearest[category] = distance

    return {category: {"distance_m": round(nearest[category])} if category in nearest else None
            for category in _CATEGORIES}
