"""Goal-driven acquisition planner for the three external verification tracks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.operational_models import stable_id
from document_engine.external_sources import source_plan


class AcquisitionAction(BaseModel):
    action_id: str
    track: Literal["ape", "gis", "cadastral_registry"]
    action: Literal["run_automatic_check", "open_assisted_check", "request_document", "await_existing_request", "complete"]
    priority: int = Field(ge=1, le=100)
    title: str
    reason: str
    responsible_party: Literal["smartbuy", "agent", "seller", "professional"]
    source_id: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    document_type: str | None = None
    requested_from: str | None = None
    blocking: bool = False


def _document_types(documents: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("document_type") or row.get("type") or "").strip().casefold()
        for row in documents
    }


def _fact_value(facts: list[dict[str, Any]], name: str) -> Any:
    for row in facts:
        if str(row.get("fact_name") or row.get("field") or "").casefold() == name.casefold():
            raw = row.get("fact_value", row.get("value"))
            return raw.get("value") if isinstance(raw, dict) and "value" in raw else raw
    return None


def build_acquisition_plan(*, property_record: dict[str, Any], documents: list[dict[str, Any]],
                           facts: list[dict[str, Any]], existing_requests: list[dict[str, Any]]) -> dict[str, Any]:
    property_id = int(property_record["id"])
    province = property_record.get("province") or property_record.get("provincia")
    doc_types = _document_types(documents)
    open_requests = {
        str(row.get("document_type") or "").casefold(): row
        for row in existing_requests if row.get("status") in {"open", "sent"}
    }
    inputs = {
        key for key, value in {
            "ape_code": _fact_value(facts, "ape_code") or _fact_value(facts, "certificate_id"),
            "comune_catastale": _fact_value(facts, "comune_catastale"),
            "foglio": _fact_value(facts, "foglio"),
            "mappale": _fact_value(facts, "mappale") or _fact_value(facts, "particella"),
            "particella": _fact_value(facts, "particella") or _fact_value(facts, "mappale"),
            "subalterno": _fact_value(facts, "subalterno"),
            "latitude": property_record.get("latitude"),
            "longitude": property_record.get("longitude"),
        }.items() if value not in (None, "")
    }
    sources = {item["source_id"]: item for item in source_plan(province=province, available_inputs=inputs)["sources"]}
    actions: list[AcquisitionAction] = []

    has_ape = any("ape" in item or "prestazione_energetica" in item for item in doc_types)
    ape_source = sources.get("sace_er") or sources.get("cened_lombardia")
    if has_ape and ape_source and ape_source["status"] == "ready":
        actions.append(_action(property_id, "ape", "open_assisted_check", 95,
            "Verifica l’APE nel registro regionale", "Il documento e gli identificativi sono disponibili.",
            "agent", source_id=ape_source["source_id"], blocking=True))
    elif has_ape:
        actions.append(_action(property_id, "ape", "request_document", 90,
            "Completa i dati per la verifica APE", "L’APE è presente ma manca il codice o l’identità catastale completa.",
            "seller", document_type="ape_supporting_data", requested_from="seller",
            required_inputs=(ape_source or {}).get("missing_inputs", []), blocking=True))
    elif "ape" in open_requests:
        actions.append(_action(property_id, "ape", "await_existing_request", 88,
            "Attendi l’APE richiesto", "Esiste già una richiesta aperta: non ne viene creata una seconda.",
            "seller", document_type="ape", requested_from="seller", blocking=True))
    else:
        actions.append(_action(property_id, "ape", "request_document", 92,
            "Richiedi l’APE al venditore", "Il documento completo non è nel fascicolo.",
            "seller", document_type="ape", requested_from="seller", blocking=True))

    if {"latitude", "longitude"}.issubset(inputs) and "rer_geoportal" in sources:
        actions.append(_action(property_id, "gis", "run_automatic_check", 80,
            "Verifica automaticamente localizzazione e vincoli", "Coordinate disponibili e fonte OGC pubblica.",
            "smartbuy", source_id="rer_geoportal"))
    else:
        actions.append(_action(property_id, "gis", "request_document", 55,
            "Acquisisci una localizzazione affidabile", "Servono coordinate per interrogare i livelli territoriali.",
            "agent", document_type="property_coordinates", requested_from="agent",
            required_inputs=["latitude", "longitude"]))

    has_visura = any("visura" in item and ("catast" in item or item == "visura") for item in doc_types)
    if has_visura:
        actions.append(_action(property_id, "cadastral_registry", "complete", 70,
            "Visura catastale acquisita", "Il documento può essere analizzato e confrontato con le altre fonti.", "smartbuy"))
    elif "visura_catastale" in open_requests:
        actions.append(_action(property_id, "cadastral_registry", "await_existing_request", 72,
            "Attendi la visura già richiesta", "La richiesta esistente resta il percorso attivo.",
            "professional", document_type="visura_catastale", requested_from="professional", blocking=True))
    else:
        actions.append(_action(property_id, "cadastral_registry", "request_document", 75,
            "Richiedi la visura catastale", "Serve accesso del titolare, acquisto telematico o professionista SISTER.",
            "professional", source_id="sister", document_type="visura_catastale",
            requested_from="professional", blocking=True))

    actions.sort(key=lambda item: item.priority, reverse=True)
    next_action = next((item for item in actions if item.action != "complete"), None)
    return {
        "property_id": property_id,
        "actions": [item.model_dump(mode="json") for item in actions],
        "next_action": next_action.model_dump(mode="json") if next_action else None,
        "autonomous_actions": sum(item.responsible_party == "smartbuy" and item.action == "run_automatic_check" for item in actions),
        "human_actions": sum(item.responsible_party != "smartbuy" and item.action not in {"complete", "await_existing_request"} for item in actions),
        "blocking_actions": sum(item.blocking and item.action != "complete" for item in actions),
    }


def _action(property_id: int, track: str, action: str, priority: int, title: str, reason: str,
            responsible_party: str, **kwargs: Any) -> AcquisitionAction:
    return AcquisitionAction(
        action_id=stable_id("acquisition-action", property_id, track, action, kwargs.get("document_type") or ""),
        track=track, action=action, priority=priority, title=title, reason=reason,
        responsible_party=responsible_party, **kwargs,
    )

