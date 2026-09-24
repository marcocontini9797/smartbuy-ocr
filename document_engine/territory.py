"""Territory profile of a property from public sources.

Seismic zone (Protezione Civile), flood and landslide hazard at the exact
position and in the municipality (ISPRA), taxable income of the municipality
and of the postcode (MEF). Each item carries its source and a plain reading;
hazards also produce the questions to ask before signing.
"""

from __future__ import annotations

from typing import Any

SEISMIC_READING = {
    "1": "zona 1, sismicità alta: la più pericolosa",
    "2": "zona 2, sismicità media",
    "3": "zona 3, sismicità bassa",
    "4": "zona 4, sismicità molto bassa",
}
SEISMIC_SOURCE = "Dipartimento della Protezione Civile – classificazione sismica dei comuni (maggio 2025)"
INCOME_SOURCE = "MEF – Dipartimento delle Finanze, dichiarazioni IRPEF (anno d'imposta 2024)"


def _seismic(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    zone = str(row["zona"]).strip()
    reading = SEISMIC_READING.get(zone[:1], f"zona {zone}")
    if len(zone) > 1:
        reading += f" (sottozona {zone})"
    return {"zone": zone, "reading": reading, "high": zone[:1] in {"1", "2"}, "source": SEISMIC_SOURCE}


def _pct(value: Any) -> float | None:
    return round(float(value), 1) if value is not None else None


def _municipal(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {"flood_population_p2_pct": _pct(row.get("flood_pop_p2_pct")), "flood_population_p3_pct": _pct(row.get("flood_pop_p3_pct")),
            "flood_area_p3_pct": _pct(row.get("flood_area_p3_pct")), "flood_area_p2_pct": _pct(row.get("flood_area_p2_pct")),
            "landslide_area_p3p4_pct": _pct((row.get("landslide_area_p3_pct") or 0) + (row.get("landslide_area_p4_pct") or 0)),
            "landslide_population_p3p4_pct": _pct(row.get("landslide_pop_p3p4_pct")),
            "source": row.get("source")}


def _incomes(rows: list[dict[str, Any]], postcode: str | None) -> dict[str, Any] | None:
    by_key = {(r["anno"], r.get("cap") or ""): r for r in rows}
    latest = by_key.get((2024, ""))
    if not latest or not latest.get("reddito_imponibile_medio_eur"):
        return None
    result: dict[str, Any] = {"year": 2024, "municipal_mean": latest["reddito_imponibile_medio_eur"],
                              "taxpayers": latest.get("contribuenti"), "source": INCOME_SOURCE}
    before = by_key.get((2019, ""))
    if before and before.get("reddito_imponibile_medio_eur"):
        result["change_since_2019"] = round(latest["reddito_imponibile_medio_eur"] / before["reddito_imponibile_medio_eur"] - 1, 3)
    local = by_key.get((2024, postcode or ""))
    if postcode and local and local.get("reddito_imponibile_medio_eur"):
        result["postcode"] = postcode
        result["postcode_mean"] = local["reddito_imponibile_medio_eur"]
        result["postcode_vs_municipal"] = round(local["reddito_imponibile_medio_eur"] / latest["reddito_imponibile_medio_eur"] - 1, 3)
    return result


def build_territory(*, seismic: dict[str, Any] | None, municipal_hazard: dict[str, Any] | None,
                    point: dict[str, Any] | None, incomes: list[dict[str, Any]], postcode: str | None,
                    point_error: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"seismic": _seismic(seismic), "hazard_municipal": _municipal(municipal_hazard),
                              "hazard_point": point, "incomes": _incomes(incomes, postcode), "alerts": [], "questions": []}
    if point_error:
        result["hazard_point_error"] = point_error
    if point:
        flood, landslide = point.get("flood_level") or 0, point.get("landslide_level") or 0
        if flood >= 2:
            result["alerts"].append({"level": "high" if flood == 3 else "medium",
                                     "text": f"L'immobile ricade in area a pericolosità idraulica {point['flood_label']}."})
            result["questions"] += [
                "L'immobile o il condominio hanno subito allagamenti? In che anno e con quali danni?",
                "Ci sono locali interrati o seminterrati, pompe di sollevamento o paratie antiallagamento?",
                "L'immobile e il condominio sono assicurati contro alluvioni e allagamenti?",
            ]
        elif flood == 1:
            result["alerts"].append({"level": "low", "text": "L'immobile ricade in area a pericolosità idraulica bassa (P1): alluvioni rare ma possibili."})
        if 3 <= landslide <= 4:
            result["alerts"].append({"level": "high", "text": f"L'immobile ricade in area a pericolosità da frana {point['landslide_label']}."})
            result["questions"] += [
                "Ci sono crepe, cedimenti o interventi di consolidamento documentati sull'edificio o sul versante?",
                "Il Comune ha emesso ordinanze o vincoli PAI che limitano lavori e ampliamenti?",
            ]
        elif landslide in {1, 2, 5}:
            result["alerts"].append({"level": "low", "text": f"Pericolosità da frana {point['landslide_label']} nel punto dell'immobile."})
    if result["seismic"] and result["seismic"]["high"]:
        result["alerts"].append({"level": "medium", "text": f"Comune in {result['seismic']['reading']}."})
        result["questions"] += [
            "L'edificio ha una verifica di vulnerabilità sismica o lavori di miglioramento sismico (Sismabonus)?",
            "In che anno è stato costruito e con quale struttura (muratura, cemento armato)?",
        ]
    return result


# Istat IPAB areas: macro-areas and the three cities with their own index.
IPAB_AREA = {"NORD-OVEST": "ITC", "NORD-EST": "ITD", "CENTRO": "ITE", "SUD": "ITFG", "ISOLE": "ITFG"}
IPAB_CITY = {"TORINO": "ITC11", "MILANO": "ITC45", "ROMA": "ITE43"}
IPAB_LABEL = {"ITC": "Nord-Ovest", "ITD": "Nord-Est", "ITE": "Centro", "ITFG": "Sud e Isole",
              "ITC11": "Torino", "ITC45": "Milano", "ITE43": "Roma", "IT": "Italia"}
IPAB_SOURCE = "Istat – indice dei prezzi delle abitazioni (IPAB), base 2025=100"


def ipab_area(area_territoriale: str | None, comune: str | None) -> str:
    return IPAB_CITY.get(str(comune or "").upper()) or IPAB_AREA.get(str(area_territoriale or "").upper(), "IT")


def price_update(rows: list[dict[str, Any]], semestre: str | None, area: str) -> dict[str, Any] | None:
    """Change of the Istat house price index from the OMI semester to the latest quarter."""
    if not semestre or "/" not in semestre:
        return None
    year, half = semestre.split("/")
    quarters = [f"{year}-Q{q}" for q in ((1, 2) if half == "1" else (3, 4))]
    by_period = {r["period"]: r for r in rows if r.get("ref_area") == area and r.get("purchase") == "ALL" and r.get("index_2025")}
    base = [by_period[q]["index_2025"] for q in quarters if q in by_period]
    if len(base) != 2 or not by_period:
        return None
    latest_period = max(by_period, key=lambda p: (int(p[:4]), int(p[-1])))
    if latest_period <= quarters[-1]:
        return None
    latest = by_period[latest_period]
    factor = latest["index_2025"] / (sum(base) / 2)
    return {"factor": round(factor, 4), "from": f"semestre OMI {semestre}", "to": latest_period.replace("-Q", " T"),
            "area": IPAB_LABEL.get(area, area), "provisional": bool(latest.get("provisional")), "source": IPAB_SOURCE}
