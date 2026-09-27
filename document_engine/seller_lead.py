"""Pre-mandate seller/buyer lead funnel: a rough, address-only estimate and
complexity read-out for someone who has not signed anything yet, built by
recombining the same OMI/territory/valuation pipeline the real per-property
routes already use (api/property_routes.py) instead of a separate one.

Nothing here requires a `properties` row, a session, or an agent account:
every function takes a service-role Supabase client and plain answers from
an anonymous quiz. Complexity scoring is pure (no DB), so it is cheap to
recompute on every step as the quiz answers grow.
"""

from __future__ import annotations

from typing import Any

from document_engine.geocoding import geocode
from document_engine.territory import build_territory
from document_engine.typology import TYPOLOGIES, typology_of
from document_engine.valuation import _STATE_BY_CONDITION, _quote, build_valuation
from llm_client import LIGHT_MODEL, free_text_call
from system_prompts import seller_report_system_prompt

_OWNERSHIP_MESSAGES = {
    "successione": ("Gli immobili ereditati richiedono in media più tempo per la voltura catastale "
                     "prima della vendita, e un atto di provenienza più articolato."),
    "donazione": ("Un immobile ricevuto in donazione può richiedere verifiche aggiuntive sulla "
                  "provenienza prima della vendita."),
    "acquisto": "Hai già la forma più semplice di atto di provenienza.",
}


def resolve_location(address: str | None, city: str | None) -> tuple[float, float] | None:
    return geocode(address, city)


def market_snapshot(client, lat: float, lon: float) -> dict[str, Any] | None:
    """Zone-level OMI data at a position: whatever `smartbuy_omi_zone_quotes`
    finds, regardless of typology (used before the quiz asks for one)."""
    try:
        zone = client.rpc("smartbuy_omi_zone_quotes", {"p_lat": lat, "p_lon": lon}).execute().data
    except Exception:
        return None
    return zone or None


def zone_price_range(zone: dict[str, Any] | None) -> dict[str, Any] | None:
    """Widest comprare (buy) range across every typology in the zone, for a
    first, coarse reveal before we know what kind of property this is."""
    quotes = [q for q in (zone or {}).get("quotes") or [] if q.get("compr_min") and q.get("compr_max")]
    if not quotes:
        return None
    return {"low": min(q["compr_min"] for q in quotes), "high": max(q["compr_max"] for q in quotes),
            "comune": next((q.get("comune") for q in quotes if q.get("comune")), None)}


def typology_price_range(zone: dict[str, Any] | None, typology_key: str | None,
                         condition: str | None = None) -> dict[str, Any] | None:
    """Per-m^2 range for one typology in the zone — refines zone_price_range
    once the quiz knows what kind of property this is, still without a
    surface (that only arrives at the last question)."""
    quotes = (zone or {}).get("quotes") or []
    typology = TYPOLOGIES.get(typology_key or "appartamento", TYPOLOGIES["appartamento"])
    wanted_state = _STATE_BY_CONDITION.get(str(condition or "").strip().casefold(), "NORMALE")
    codes = typology.omi_codes or ("20", "21", "19")
    for code in codes:
        quote, state = _quote(quotes, code, wanted_state)
        if quote:
            return {"low": quote["compr_min"], "high": quote["compr_max"], "state": state, "typology": typology.label}
    return None


def territory_snapshot(client, zone: dict[str, Any] | None) -> dict[str, Any] | None:
    """Seismic + hazard + income profile of the zone's municipality, reusing
    build_territory (document_engine/territory.py) — the same function the
    Rischi tab already renders for a real property."""
    comune_cat = (zone or {}).get("comune_cat")
    if not comune_cat:
        return None
    try:
        comune = (client.table("istat_comuni").select("*").eq("codice_catastale", comune_cat)
                  .limit(1).execute().data or [None])[0]
    except Exception:
        comune = None
    if not comune:
        return None
    codice_istat = comune.get("codice_istat")

    def one(table: str) -> dict[str, Any] | None:
        try:
            return (client.table(table).select("*").eq("codice_istat", codice_istat)
                    .limit(1).execute().data or [None])[0]
        except Exception:
            return None

    try:
        incomes = client.table("irpef_incomes").select("*").eq("codice_istat", codice_istat).execute().data or []
    except Exception:
        incomes = []
    return build_territory(seismic=one("seismic_zones"), municipal_hazard=one("municipal_hazard"),
                           point=None, incomes=incomes, postcode=None)


def full_estimate(*, city: str | None, typology_key: str | None, contract: str | None,
                  condition: str | None, floor: int | None, elevator: bool | None,
                  surface_m2: float | None, zone: dict[str, Any] | None) -> dict[str, Any]:
    """The precise, surface-aware estimate for the final report — the same
    build_valuation the real per-property Valutazione tab uses, fed a
    synthetic property_record instead of a database row."""
    synthetic = {"city": city, "typology": typology_key, "contract": contract or "vendita",
                 "condition": condition, "floor": floor, "elevator": elevator, "surface_m2": surface_m2}
    return build_valuation(property_record=synthetic, zone=zone, facts=[], yield_stats=None,
                           comparables=None, calibration=None, price_update=None, reference=None)


_COMPLEXITY_FACTORS = (
    ("is_condominium", True, "Condominio",
     "In condominio servono in più regolamento, verbali assembleari e situazione pagamenti: "
     "3 documenti che una vendita senza condominio non richiede.",
     "Nessuna documentazione condominiale da recuperare: un ostacolo in meno."),
    ("is_rented", True, "Locazione in corso",
     "Un immobile locato ha vincoli specifici alla vendita (es. diritto di prelazione del conduttore "
     "in alcuni casi): un dettaglio da gestire con attenzione.",
     "Nessun vincolo di locazione in corso: un altro punto a favore."),
)


def complexity_factors(answers: dict[str, Any]) -> dict[str, Any]:
    """Pure, DB-free scoring from the quiz answers alone: which situational
    factors make a private, unassisted sale more complex, plus how many of
    the three key documents the person already says they have."""
    factors: list[dict[str, Any]] = []
    complexity = 0
    for key, trigger_value, label, message_present, message_absent in _COMPLEXITY_FACTORS:
        if answers.get(key) is None:
            continue  # not answered yet: Pydantic dumps every field, so `in` alone can't tell
        present = bool(answers[key]) == trigger_value
        if present:
            complexity += 1
        factors.append({"key": key, "label": label, "present": present,
                        "message": message_present if present else message_absent})

    ownership = answers.get("ownership_origin")
    if ownership:
        present = ownership in ("successione", "donazione")
        if present:
            complexity += 1
        factors.append({"key": "ownership_origin", "label": "Provenienza", "present": present,
                        "message": _OWNERSHIP_MESSAGES.get(ownership, "")})

    documents_ready = answers.get("documents_ready") or []
    readiness = len([d for d in ("visura", "planimetria", "ape") if d in documents_ready])
    return {"factors": factors, "complexity_score": complexity, "complexity_max": 3,
            "readiness_score": readiness, "readiness_max": 3}


def compose_seller_report(*, answers: dict[str, Any], estimate: dict[str, Any],
                          complexity: dict[str, Any]) -> str:
    """AI narrative, strictly grounded in the structured facts already
    computed above — same pattern as document_engine/request_composer.py:
    the model phrases what we already know, it does not decide what to say."""
    lines = [f"Indirizzo: {answers.get('address', 'N/D')}, {answers.get('city', 'N/D')}",
             f"Obiettivo: {answers.get('contract', 'vendita')}"]
    if estimate.get("status") != "unavailable" and estimate.get("methods"):
        method = estimate["methods"][0]
        lines.append(f"Stima di mercato: {method['low']:,}–{method['high']:,} EUR ({method.get('explanation', '')})".replace(",", "."))
    else:
        lines.append(f"Stima di mercato non disponibile: {estimate.get('reason', 'dati insufficienti')}")
    lines.append(f"Prontezza documentale: {complexity['readiness_score']}/{complexity['readiness_max']} documenti chiave già pronti")
    present_factors = [f["label"] for f in complexity["factors"] if f["present"]]
    lines.append("Complessità rilevate: " + (", ".join(present_factors) if present_factors else "nessuna delle situazioni verificate"))
    for factor in complexity["factors"]:
        lines.append(f"- {factor['label']}: {factor['message']}")
    try:
        return free_text_call(system=seller_report_system_prompt(), user="\n".join(lines),
                              temperature=0.3, model=LIGHT_MODEL).strip()
    except Exception:
        return ("Ecco il riepilogo di quanto emerso: " + " ".join(lines[2:4]) + " "
                + " ".join(present_factors and [f"Punti di attenzione: {', '.join(present_factors)}."] or []))
