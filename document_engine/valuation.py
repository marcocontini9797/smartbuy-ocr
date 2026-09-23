"""Indicative market value range, with the method suited to the asset class.

* residenziale (flat): market comparison on the OMI "Abitazioni civili" range
  of the zone for the conservation state, times the gross surface, with small
  declared corrections (floor/lift, energy class);
* commerciale (shop): OMI "Negozi" market comparison and income approach
  (OMI market rent, or the actual rent of a lease, capitalised at a declared
  gross yield range), averaged.

Every assumption is returned with the result. This is an indicative range
from public OMI quotations, not an appraisal.
"""

from __future__ import annotations

from typing import Any

from document_engine.cross_validation import effective_facts, norm_comune, norm_energy_class, parse_number

# Gross yield range used to capitalise retail rents (declared assumption).
RETAIL_GROSS_YIELD = (0.06, 0.08)
MAX_TOTAL_ADJUSTMENT = 0.20

_STATE_BY_CONDITION = {
    "ottimo": "OTTIMO", "ristrutturato": "OTTIMO", "nuovo": "OTTIMO", "nuova costruzione": "OTTIMO",
    "da ristrutturare": "SCADENTE", "scadente": "SCADENTE",
}
_STATE_LABEL = {"OTTIMO": "ottimo", "NORMALE": "normale", "SCADENTE": "scadente"}
_ENERGY_ADJUSTMENT = {"A4": 0.05, "A3": 0.05, "A2": 0.05, "A1": 0.05, "A+": 0.05, "B": 0.03,
                      "C": 0.0, "D": 0.0, "E": -0.02, "F": -0.04, "G": -0.06}


def _round(value: float, step: int = 1000) -> int:
    return int(round(value / step) * step)


def _fact(facts: list[dict[str, Any]], *names: str) -> Any:
    for fact in effective_facts(facts):
        if fact.get("fact_name") in names:
            value = fact.get("fact_value")
            return value.get("value") if isinstance(value, dict) and "value" in value else value
    return None


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


def build_valuation(
    *,
    property_record: dict[str, Any],
    zone: dict[str, Any] | None,
    facts: list[dict[str, Any]] | None = None,
    document_problems: int = 0,
) -> dict[str, Any]:
    facts = facts or []
    kind = property_record.get("property_type") or "residenziale"
    result: dict[str, Any] = {"property_type": kind, "status": "unavailable", "methods": [], "adjustments": [], "caveats": []}

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
    quotes = zone["quotes"]
    result["zone"] = {key: zone.get(key) for key in ("zona", "fascia", "descrizione", "semestre")}
    result["zone"]["comune"] = next((q.get("comune") for q in quotes if q.get("comune")), None)
    result["surface"] = {"value": surface, "source": surface_source,
                         "note": "Le quotazioni OMI si riferiscono alla superficie lorda (commerciale)."}

    if kind == "commerciale":
        quote, state = _quote(quotes, "5", wanted_state)
        if not quote:
            result["reason"] = "Nessuna quotazione OMI per negozi in questa zona."
            return result
        comp = (quote["compr_min"] * surface, quote["compr_max"] * surface)
        result["methods"].append({
            "name": "Comparativo (quotazioni OMI negozi)", "low": _round(comp[0]), "high": _round(comp[1]),
            "explanation": f"{quote['compr_min']:,.0f}–{quote['compr_max']:,.0f} €/m² × {surface:g} m² (stato {_STATE_LABEL.get(state, state)})"
                           .replace(",", "."),
        })
        actual_rent = parse_number(_fact(facts, "canone_mensile_eur"))
        low_yield, high_yield = RETAIL_GROSS_YIELD
        if actual_rent:
            rent = (actual_rent * 12, actual_rent * 12)
            rent_text = f"canone del contratto {actual_rent:,.0f} €/mese".replace(",", ".")
        elif quote.get("loc_min") and quote.get("loc_max"):
            rent = (quote["loc_min"] * surface * 12, quote["loc_max"] * surface * 12)
            rent_text = f"canone di mercato OMI {quote['loc_min']:g}–{quote['loc_max']:g} €/m² al mese".replace(".", ",")
        else:
            rent = None
        if rent:
            income = (rent[0] / high_yield, rent[1] / low_yield)
            result["methods"].append({
                "name": "Reddituale (capitalizzazione del canone)", "low": _round(income[0]), "high": _round(income[1]),
                "explanation": f"{rent_text}, capitalizzato a un rendimento lordo del {low_yield:.0%}–{high_yield:.0%}",
            })
            result["caveats"].append(f"Il rendimento lordo {low_yield:.0%}–{high_yield:.0%} è un'ipotesi di mercato per negozi: "
                                     "posizione, visibilità e durata del contratto possono spostarlo.")
        lows = [m["low"] for m in result["methods"]]
        highs = [m["high"] for m in result["methods"]]
        low, high = sum(lows) / len(lows), sum(highs) / len(highs)
        if len(result["methods"]) == 2:
            mids = [(m["low"] + m["high"]) / 2 for m in result["methods"]]
            if abs(mids[0] - mids[1]) / min(mids) > 0.30:
                higher = "reddituale" if mids[1] > mids[0] else "comparativo"
                result["caveats"].append(
                    f"I due metodi divergono di oltre il 30% (più alto il {higher}): accade nelle vie commerciali di pregio "
                    "o dove i canoni non sono allineati ai prezzi. Serve un confronto con compravendite reali della via.")
    else:
        quote, state = _quote(quotes, "20", wanted_state)
        if not quote:
            quote, state = _quote(quotes, "21", wanted_state)
        if not quote:
            result["reason"] = "Nessuna quotazione OMI residenziale in questa zona."
            return result
        base = (quote["compr_min"] * surface, quote["compr_max"] * surface)
        result["methods"].append({
            "name": f"Comparativo (quotazioni OMI {quote['tipologia'].lower()})", "low": _round(base[0]), "high": _round(base[1]),
            "explanation": f"{quote['compr_min']:,.0f}–{quote['compr_max']:,.0f} €/m² × {surface:g} m² (stato {_STATE_LABEL.get(state, state)})"
                           .replace(",", "."),
        })
        result["adjustments"] = _residential_adjustments(property_record, energy_class)
        total = max(-MAX_TOTAL_ADJUSTMENT, min(MAX_TOTAL_ADJUSTMENT, sum(a["pct"] for a in result["adjustments"])))
        low, high = base[0] * (1 + total), base[1] * (1 + total)
        if result["adjustments"]:
            result["caveats"].append("I correttivi (piano, ascensore, classe energetica) sono percentuali indicative di prassi estimativa.")

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
    result["range"] = {"low": _round(low), "mid": _round((low + high) / 2), "high": _round(high),
                       "per_sqm_low": round(low / surface), "per_sqm_high": round(high / surface)}
    asking = parse_number(property_record.get("asking_price"))
    if asking:
        position = "below" if asking < low else "above" if asking > high else "within"
        result["asking_price"] = {"value": asking, "position": position,
                                  "vs_mid_pct": round((asking - (low + high) / 2) / ((low + high) / 2), 3)}
    return result
