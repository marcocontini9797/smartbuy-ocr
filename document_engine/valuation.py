"""Indicative market value range, with the method suited to the asset class.

residenziale (flat)
    Market comparison: OMI range of the zone for the typology matching the
    cadastral category (A/1 signorili, A/2 civili, A/3-A/6 economico,
    A/7-A/8 ville) and the conservation state, times the gross surface, with
    declared corrections (floor/lift, energy class). Garages and parking
    spaces (C/6) listed in the documents are added with the OMI "Box" range.
    The OMI market rent gives the expected rent and the gross yield at the
    asking price.

commerciale (shop)
    OMI "Negozi" comparison and direct capitalisation: annual rent (the actual
    lease rent when a lease is on file, otherwise the zone's OMI rent) divided
    by the market gross yield of the municipality, i.e. the quartiles of
    rent/price over all its OMI zones. The zone's own implied yield is not used
    for capitalisation (that would reproduce the comparison) but is reported.

Every input and assumption is returned with the result. Indicative range from
public OMI quotations, not an appraisal.
"""

from __future__ import annotations

from statistics import median, quantiles
from typing import Any

from document_engine.cross_validation import effective_facts, norm_categoria, norm_comune, norm_energy_class, parse_number

# Used only when the municipality/province/Italy yield statistics are unavailable.
FALLBACK_RETAIL_YIELD = {"p25": 0.055, "p50": 0.063, "p75": 0.076, "scope": "italia", "label": "Italia (valore di riserva)", "n": 0}
MAX_TOTAL_ADJUSTMENT = 0.20

# Average discount between asking and final price, Banca d'Italia - Tecnoborsa -
# Agenzia delle Entrate "Sondaggio congiunturale sul mercato delle abitazioni",
# 2nd quarter 2026. The North-West is not published separately: national value.
NEGOTIATION_DISCOUNT = {"NORD-EST": 0.05, "NORD-OVEST": 0.07, "CENTRO": 0.09, "SUD": 0.09, "ISOLE": 0.09}
NEGOTIATION_DISCOUNT_SOURCE = "Sondaggio congiunturale Banca d'Italia – Tecnoborsa – Agenzia Entrate, 2° trimestre 2026"
MIN_COMPARABLES = 3
MIN_CALIBRATION_SALES = 5

_STATE_BY_CONDITION = {
    "ottimo": "OTTIMO", "ristrutturato": "OTTIMO", "nuovo": "OTTIMO", "nuova costruzione": "OTTIMO",
    "da ristrutturare": "SCADENTE", "scadente": "SCADENTE",
}
_STATE_LABEL = {"OTTIMO": "ottimo", "NORMALE": "normale", "SCADENTE": "scadente"}
_ENERGY_ADJUSTMENT = {"A4": 0.05, "A3": 0.05, "A2": 0.05, "A1": 0.05, "A+": 0.05, "B": 0.03,
                      "C": 0.0, "D": 0.0, "E": -0.02, "F": -0.04, "G": -0.06}
# OMI typology codes: 19 signorili, 20 civili, 21 tipo economico, 1 ville e villini, 13 box, 5 negozi.
_TYPOLOGY_BY_CATEGORY = {"A/1": "19", "A/2": "20", "A/3": "21", "A/4": "21", "A/5": "21", "A/6": "21", "A/7": "1", "A/8": "1"}


def _round(value: float, step: int = 1000) -> int:
    return int(round(value / step) * step)


def _euro(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _fact(facts: list[dict[str, Any]], *names: str) -> Any:
    for fact in effective_facts(facts):
        if fact.get("fact_name") in names:
            value = fact.get("fact_value")
            return value.get("value") if isinstance(value, dict) and "value" in value else value
    return None


def _cadastral_units(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cadastral units (category, consistenza) found in visura/atto facts."""
    units = []
    for fact in effective_facts(facts):
        name = fact.get("fact_name")
        if name not in {"riferimento", "riferimenti_catastali"}:
            continue
        value = fact.get("fact_value")
        value = value.get("value") if isinstance(value, dict) and "value" in value else value
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                units.append({"categoria": norm_categoria(item.get("categoria")), "consistenza": item.get("consistenza"),
                              "subalterno": item.get("subalterno")})
    return units


def _quote(quotes: list[dict[str, Any]], cod_tip: str, state: str) -> tuple[dict[str, Any] | None, str]:
    """Quotation for a typology and state, falling back to NORMALE."""
    by_state = {q["stato"]: q for q in quotes if q.get("cod_tip") == cod_tip and q.get("compr_min")}
    if state in by_state:
        return by_state[state], state
    if "NORMALE" in by_state:
        return by_state["NORMALE"], "NORMALE"
    return (next(iter(by_state.values())), next(iter(by_state))) if by_state else (None, state)


def _surface(property_record: dict[str, Any], facts: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    if property_record.get("surface_m2"):
        return float(property_record["surface_m2"]), "scheda immobile"
    for name, label in (("superficie_commerciale_mq", "documenti (superficie commerciale)"),
                        ("superficie_dichiarata_mq", "atto (superficie dichiarata)"),
                        ("superficie_catastale_mq", "visura (superficie catastale)")):
        value = parse_number(_fact(facts, name))
        if value:
            return value, label
    return None, None


def _residential_adjustments(property_record: dict[str, Any], energy_class: str | None) -> list[dict[str, Any]]:
    adjustments = []
    if energy_class and _ENERGY_ADJUSTMENT.get(energy_class):
        adjustments.append({"label": f"Classe energetica {energy_class}", "pct": _ENERGY_ADJUSTMENT[energy_class]})
    floor, elevator = property_record.get("floor"), property_record.get("elevator")
    if floor == 0:
        adjustments.append({"label": "Piano terra", "pct": -0.05})
    elif floor is not None and floor >= 3 and elevator is False:
        adjustments.append({"label": f"Piano {floor} senza ascensore", "pct": -0.08})
    elif floor is not None and floor >= 4 and elevator is True:
        adjustments.append({"label": f"Piano alto ({floor}) con ascensore", "pct": 0.03})
    return adjustments


def _pct(value: float) -> str:
    return f"{value:.1%}".replace(".", ",")


def _mid(quote: dict[str, Any], low_key: str, high_key: str) -> float:
    return (quote[low_key] + quote[high_key]) / 2


def _confidence(checks: list[tuple[bool, str]]) -> dict[str, Any]:
    missing = [label for ok, label in checks if not ok]
    score = 1 - len(missing) / len(checks)
    level = "alta" if score >= 0.8 else "media" if score >= 0.5 else "bassa"
    return {"level": level, "score": round(score, 2), "missing": missing}


def _quantiles(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    if len(ordered) < 4:
        return ordered[0], median(ordered), ordered[-1]
    q1, q2, q3 = quantiles(ordered, n=4)
    return q1, q2, q3


def comparables_method(comparables: list[dict[str, Any]], surface: float, area: str | None) -> dict[str, Any] | None:
    """Market comparison on listings (net of the negotiation discount) and known sales."""
    discount = NEGOTIATION_DISCOUNT.get(str(area or "").upper(), 0.07)
    per_sqm = []
    for comp in comparables:
        price, comp_surface = parse_number(comp.get("price")), parse_number(comp.get("surface_m2"))
        if not price or not comp_surface:
            continue
        per_sqm.append(price / comp_surface * (1 - discount if comp.get("kind") == "annuncio" else 1))
    if len(per_sqm) < MIN_COMPARABLES:
        return None
    low, mid, high = _quantiles(per_sqm)
    listings = sum(1 for c in comparables if c.get("kind") == "annuncio")
    return {
        "name": f"Comparabili ({len(per_sqm)}: {listings} annunci, {len(per_sqm) - listings} vendite)",
        "low": _round(low * surface), "mid": _round(mid * surface), "high": _round(high * surface),
        "weight": round(min(0.6, 0.1 * len(per_sqm)), 2),
        "explanation": f"{_euro(low)}–{_euro(high)} €/m² (mediana {_euro(mid)}) × {surface:g} m²; prezzi degli annunci "
                       f"ridotti del {discount:.0%} di sconto medio di trattativa ({NEGOTIATION_DISCOUNT_SOURCE})",
    }


def calibration_from_outcomes(outcomes: list[dict[str, Any]], comune: str | None) -> dict[str, Any]:
    """Median ratio sale price / SmartBuy estimate over the recorded sales."""
    usable = [o for o in outcomes if parse_number(o.get("estimate_mid")) and parse_number(o.get("sale_price"))]
    local = [o for o in usable if comune and norm_comune(o.get("comune") or "") == norm_comune(comune)]
    scope, sample = ("comune", local) if len(local) >= MIN_CALIBRATION_SALES else ("tutte le vendite", usable)
    ratios = [parse_number(o["sale_price"]) / parse_number(o["estimate_mid"]) for o in sample]
    result: dict[str, Any] = {"n": len(ratios), "scope": scope, "applied": len(ratios) >= MIN_CALIBRATION_SALES}
    if ratios:
        result["factor"] = round(median(ratios), 4)
        result["mean_abs_error"] = round(sum(abs(r - 1) for r in ratios) / len(ratios), 4)
    return result


def build_valuation(
    *,
    property_record: dict[str, Any],
    zone: dict[str, Any] | None,
    facts: list[dict[str, Any]] | None = None,
    yield_stats: dict[str, Any] | None = None,
    comparables: list[dict[str, Any]] | None = None,
    calibration: dict[str, Any] | None = None,
    document_problems: int = 0,
) -> dict[str, Any]:
    facts = facts or []
    kind = property_record.get("property_type") or "residenziale"
    result: dict[str, Any] = {"property_type": kind, "status": "unavailable", "methods": [], "adjustments": [],
                              "additions": [], "caveats": []}

    if not zone or not zone.get("quotes"):
        result["reason"] = ("Zona OMI non individuata: servono le coordinate dell'immobile "
                            "(indirizzo riconoscibile) in un comune coperto dalle quotazioni OMI.")
        return result
    zone_city = next((q.get("comune") for q in zone["quotes"] if q.get("comune")), None)
    if property_record.get("city") and zone_city and norm_comune(zone_city) != norm_comune(property_record["city"]):
        result["reason"] = (f"La posizione trovata ricade nel comune di {zone_city.title()}, non in quello dell'immobile "
                            f"({property_record['city']}): controlla l'indirizzo nella scheda.")
        return result
    surface, surface_source = _surface(property_record, facts)
    if not surface:
        result["reason"] = "Manca la superficie: inseriscila nella scheda o carica un documento che la riporti."
        return result

    condition = str(property_record.get("condition") or "").strip().casefold()
    wanted_state = _STATE_BY_CONDITION.get(condition, "NORMALE")
    energy_class = norm_energy_class(_fact(facts, "classe_energetica", "energy_class") or property_record.get("energy_class"))
    units = _cadastral_units(facts)
    quotes = zone["quotes"]
    result["zone"] = {key: zone.get(key) for key in ("zona", "fascia", "descrizione", "semestre")}
    result["zone"]["comune"] = zone_city
    result["surface"] = {"value": surface, "source": surface_source,
                         "note": "Le quotazioni OMI si riferiscono alla superficie lorda (commerciale)."}

    if kind == "commerciale":
        quote, state = _quote(quotes, "5", wanted_state)
        if not quote:
            result["reason"] = "Nessuna quotazione OMI per negozi in questa zona."
            return result
        comp = (quote["compr_min"] * surface, quote["compr_max"] * surface)
        comparative = {"name": "Comparativo (quotazioni OMI negozi)", "low": _round(comp[0]), "high": _round(comp[1]),
                       "mid": _round(_mid(quote, "compr_min", "compr_max") * surface),
                       "explanation": f"{_euro(quote['compr_min'])}–{_euro(quote['compr_max'])} €/m² × {surface:g} m² "
                                      f"(stato {_STATE_LABEL.get(state, state)})"}
        result["methods"].append(comparative)

        actual_rent = parse_number(_fact(facts, "canone_mensile_eur"))
        yields = yield_stats or FALLBACK_RETAIL_YIELD
        if actual_rent:
            rent = (actual_rent * 12, actual_rent * 12, actual_rent * 12)
            rent_text = f"canone del contratto in essere {_euro(actual_rent)} €/mese"
        elif quote.get("loc_min") and quote.get("loc_max"):
            rent = (quote["loc_min"] * surface * 12, _mid(quote, "loc_min", "loc_max") * surface * 12, quote["loc_max"] * surface * 12)
            rent_text = f"canone di mercato OMI della zona {quote['loc_min']:g}–{quote['loc_max']:g} €/m² al mese".replace(".", ",")
        else:
            rent = None
        if rent:
            income = {"name": "Reddituale (capitalizzazione diretta del canone)",
                      "low": _round(rent[0] / yields["p75"]), "high": _round(rent[2] / yields["p25"]), "mid": _round(rent[1] / yields["p50"]),
                      "explanation": f"{rent_text}, diviso il rendimento lordo di mercato dei negozi "
                                     f"({yields['label']}: {_pct(yields['p25'])}–{_pct(yields['p75'])}, mediana {_pct(yields['p50'])})"}
            result["methods"].append(income)
            result["yield"] = {**yields, "zone_implied": round(_mid(quote, "loc_min", "loc_max") * 12 / _mid(quote, "compr_min", "compr_max"), 4)
                               if quote.get("loc_min") else None, "source": "quotazioni OMI (canone annuo / prezzo)"}
            if not yield_stats:
                result["caveats"].append("Rendimento di mercato non disponibile per il comune: usato il valore nazionale di riserva.")
        # A lease on file is specific evidence: it weighs more than the zone average.
        weights = [0.4, 0.6] if actual_rent and len(result["methods"]) == 2 else [1 / len(result["methods"])] * len(result["methods"])
        low = sum(w * m["low"] for w, m in zip(weights, result["methods"]))
        high = sum(w * m["high"] for w, m in zip(weights, result["methods"]))
        mid = sum(w * m["mid"] for w, m in zip(weights, result["methods"]))
        if len(result["methods"]) == 2:
            mids = [m["mid"] for m in result["methods"]]
            if abs(mids[0] - mids[1]) / min(mids) > 0.30:
                higher = "reddituale" if mids[1] > mids[0] else "comparativo"
                result["caveats"].append(
                    f"I due metodi divergono di oltre il 30% (più alto il {higher}): accade nelle vie commerciali di pregio "
                    "o dove i canoni della zona non sono allineati ai prezzi. Serve un confronto con compravendite reali della via.")
        result["confidence"] = _confidence([
            (surface_source is not None, "superficie"),
            (bool(property_record.get("condition")), "stato di conservazione"),
            (any(u["categoria"] for u in units), "categoria catastale da visura"),
            (bool(actual_rent) or rent is not None, "canone (contratto o mercato)"),
            (bool(yield_stats) and yields.get("scope") != "italia", "rendimento di mercato locale"),
        ])
    else:
        category = next((u["categoria"] for u in units if u["categoria"] and u["categoria"].startswith("A/")), None)
        typology = _TYPOLOGY_BY_CATEGORY.get(category or "", "20")
        quote, state = _quote(quotes, typology, wanted_state)
        if not quote and typology != "20":
            quote, state = _quote(quotes, "20", wanted_state)
            result["caveats"].append(f"Nessuna quotazione OMI per la tipologia della categoria {category}: usate le abitazioni civili.")
        if not quote:
            quote, state = _quote(quotes, "21", wanted_state)
        if not quote:
            result["reason"] = "Nessuna quotazione OMI residenziale in questa zona."
            return result
        base = (quote["compr_min"] * surface, _mid(quote, "compr_min", "compr_max") * surface, quote["compr_max"] * surface)
        result["methods"].append({
            "name": f"Comparativo (quotazioni OMI {quote['tipologia'].lower()})", "low": _round(base[0]), "high": _round(base[2]),
            "mid": _round(base[1]),
            "explanation": f"{_euro(quote['compr_min'])}–{_euro(quote['compr_max'])} €/m² × {surface:g} m² "
                           f"(stato {_STATE_LABEL.get(state, state)}"
                           + (f", tipologia scelta dalla categoria catastale {category})" if category else ")"),
        })
        result["adjustments"] = _residential_adjustments(property_record, energy_class)
        total = max(-MAX_TOTAL_ADJUSTMENT, min(MAX_TOTAL_ADJUSTMENT, sum(a["pct"] for a in result["adjustments"])))
        low, mid, high = (value * (1 + total) for value in base)
        if result["adjustments"]:
            result["caveats"].append("I correttivi (piano, ascensore, classe energetica) sono percentuali indicative di prassi estimativa.")

        box_quote, _ = _quote(quotes, "13", "NORMALE")
        for unit in units:
            if unit["categoria"] != "C/6":
                continue
            box_surface = parse_number(unit.get("consistenza"))
            if box_quote and box_surface:
                add = (box_quote["compr_min"] * box_surface, _mid(box_quote, "compr_min", "compr_max") * box_surface,
                       box_quote["compr_max"] * box_surface)
                result["additions"].append({"label": f"Box / posto auto (C/6, {box_surface:g} m²)", "low": _round(add[0]),
                                            "high": _round(add[2]), "mid": _round(add[1]),
                                            "explanation": f"{_euro(box_quote['compr_min'])}–{_euro(box_quote['compr_max'])} €/m² (OMI box)"})
                low, mid, high = low + add[0], mid + add[1], high + add[2]
            else:
                result["caveats"].append("Nei documenti c'è un box o posto auto (C/6) non valutato: manca la superficie o la quotazione OMI.")

        if quote.get("loc_min") and quote.get("loc_max"):
            rent_month = (quote["loc_min"] * surface, _mid(quote, "loc_min", "loc_max") * surface, quote["loc_max"] * surface)
            result["market_rent"] = {"low": round(rent_month[0], -1), "mid": round(rent_month[1], -1), "high": round(rent_month[2], -1),
                                     "explanation": f"{quote['loc_min']:g}–{quote['loc_max']:g} €/m² al mese (OMI)".replace(".", ",")}
        if yield_stats:
            result["yield"] = {**yield_stats, "source": "quotazioni OMI abitazioni (canone annuo / prezzo)"}
        result["confidence"] = _confidence([
            (surface_source is not None, "superficie"),
            (bool(property_record.get("condition")), "stato di conservazione"),
            (category is not None, "categoria catastale da visura"),
            (energy_class is not None, "classe energetica"),
            (property_record.get("floor") is not None, "piano"),
        ])

    comps = comparables_method(comparables or [], surface, zone.get("area_territoriale"))
    if comps:
        weight = comps.pop("weight")
        result["methods"].append(comps)
        # Comparables price the main unit only: garages are added on top as above.
        extra = {key: sum(a[key] for a in result["additions"]) for key in ("low", "mid", "high")}
        low = (1 - weight) * low + weight * (comps["low"] + extra["low"])
        mid = (1 - weight) * mid + weight * (comps["mid"] + extra["mid"])
        high = (1 - weight) * high + weight * (comps["high"] + extra["high"])
        result["comparables_weight"] = weight
    elif comparables:
        result["caveats"].append(f"Comparabili inseriti: {len(comparables)}. Ne servono almeno {MIN_COMPARABLES} per usarli nella stima.")

    # Pre-calibration estimate: what gets stored with a real sale, so calibration never compounds.
    uncalibrated = {"low": _round(low), "mid": _round(mid), "high": _round(high)}
    if calibration and calibration.get("n"):
        result["calibration"] = calibration
        if calibration["applied"]:
            factor = calibration["factor"]
            low, mid, high = low * factor, mid * factor, high * factor
            result["adjustments"].append({"label": f"Calibrazione su {calibration['n']} vendite reali ({calibration['scope']})",
                                          "pct": round(factor - 1, 4)})
        else:
            result["caveats"].append(f"Vendite reali registrate: {calibration['n']}. Dalla {MIN_CALIBRATION_SALES}ª la stima "
                                     "verrà calibrata sull'errore misurato.")

    if state != wanted_state:
        result["caveats"].append(f"Nessuna quotazione per lo stato '{_STATE_LABEL.get(wanted_state, wanted_state)}': "
                                 f"usato lo stato '{_STATE_LABEL.get(state, state)}'.")
    if not property_record.get("condition"):
        result["caveats"].append("Stato di conservazione non indicato: considerato normale.")
    if document_problems:
        result["caveats"].append(f"Ci sono {document_problems} problemi documentali aperti: possono ridurre il valore "
                                 "(vedi le schede Documenti e Trattativa).")
    result["caveats"].append(f"Stima indicativa sulle quotazioni OMI {zone.get('semestre')} dell'Agenzia delle Entrate: "
                             "non è una perizia.")

    result["status"] = "ok"
    result["range"] = {"low": _round(low), "mid": _round(mid), "high": _round(high),
                       "per_sqm_low": round(low / surface), "per_sqm_high": round(high / surface), "uncalibrated": uncalibrated}
    asking = parse_number(property_record.get("asking_price"))
    if asking:
        position = "below" if asking < low else "above" if asking > high else "within"
        result["asking_price"] = {"value": asking, "position": position, "vs_mid_pct": round((asking - mid) / mid, 3)}
        if result.get("market_rent"):
            result["asking_price"]["gross_yield"] = round(result["market_rent"]["mid"] * 12 / asking, 4)
    return result
