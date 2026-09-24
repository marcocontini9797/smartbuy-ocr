"""Landslide and flood hazard at the property's exact position (ISPRA IdroGEO).

Queries the ISPRA national hazard mosaics through their public WMS
(GetFeatureInfo): flood scenarios P1-P3 (Mosaicatura 2020, D.Lgs. 49/2010) and
landslide classes P1-P4 plus "aree di attenzione" (Mosaicatura PAI 2024).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WMS_URL = "https://idrogeo.isprambiente.it/geoserver/idrogeo/ows"
SOURCE = "ISPRA IdroGEO – mosaicature nazionali di pericolosità (frane PAI 2024, alluvioni 2020)"
FLOOD_LABEL = {0: "nessuna", 1: "bassa (P1, alluvioni rare)", 2: "media (P2, tempo di ritorno 100–200 anni)",
               3: "elevata (P3, tempo di ritorno 20–50 anni)"}
LANDSLIDE_LABEL = {0: "nessuna", 1: "moderata (P1)", 2: "media (P2)", 3: "elevata (P3)", 4: "molto elevata (P4)",
                   5: "area di attenzione (AA)"}


def _feature_info(layer: str, lat: float, lon: float, timeout: float) -> str:
    """Plain-text GetFeatureInfo: attributes only (the JSON format ships the whole regional polygon)."""
    d = 0.0003  # ~30 m box around the point; the query pixel is its centre
    params = {"service": "WMS", "version": "1.1.1", "request": "GetFeatureInfo", "layers": layer, "query_layers": layer,
              "styles": "", "srs": "EPSG:4326", "bbox": f"{lon - d},{lat - d},{lon + d},{lat + d}", "width": 101,
              "height": 101, "x": 50, "y": 50, "info_format": "text/plain", "feature_count": 20}
    request = Request(f"{WMS_URL}?{urlencode(params)}", headers={"User-Agent": "SmartBuy/1.0"})
    with urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
    if "ServiceException" in text:
        raise RuntimeError(f"ISPRA WMS error for {layer}")
    return text


def flood_level(info: str) -> int:
    return max((int(level) for level in re.findall(r"pericolosita_idraulica_p(\d)'", info)), default=0)


def landslide_level(info: str) -> int:
    levels = []
    for code in re.findall(r"^cod_per_it = (\S+)", info, re.M):
        if code.isdigit():
            levels.append(int(code))
        elif code.upper() == "AA":
            levels.append(5)
    # P1..P4 outrank an "area di attenzione" (5), a zone still to be studied.
    real = [level for level in levels if 1 <= level <= 4]
    return max(real) if real else (5 if 5 in levels else 0)


def point_hazards(lat: float, lon: float, timeout: float = 25) -> dict[str, Any]:
    flood = flood_level(_feature_info("pericolosita_alluvioni", lat, lon, timeout))
    landslide = landslide_level(_feature_info("pericolosita_frane", lat, lon, timeout))
    return {"flood_level": flood, "flood_label": FLOOD_LABEL[flood],
            "landslide_level": landslide, "landslide_label": LANDSLIDE_LABEL[landslide], "source": SOURCE}
