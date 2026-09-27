"""Cadastre and land-registry data bought from Openapi for a property.

Every paid call needs the agent's explicit confirmation (confirm_cost_eur equal
to the list price shown), is recorded in property_registry_checks with its
cost, and is not repeated when a result for the same unit already exists.
The prospetto and the mortgage inspection become documents of the property,
so checklist, cross-validation and red flags use them like uploaded ones.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.document_routes import _insert_one, persist_document_facts, store_original
from api.property_routes import _located, _zone, get_property
from api.session import user_client
from document_engine import registry
from integrations import openapi_catasto
from integrations.openapi_catasto import CatastoClient, OpenapiError, OpenapiPending

router = APIRouter(prefix="/api/v1", tags=["registry"])
APE_LOOKUP_URL = ("https://energia.regione.emilia-romagna.it/riqualificazione-edifici-e-certificazione-energetica/"
                  "certificazioneenergetica/visura-ape-ricerca-di-un-attestato-di-prestazione-energetica-ape")
PLANIMETRIA_DELEGA_URL = ("https://www.agenziaentrate.gov.it/portale/documents/20143/4490418/"
                          "Modulo_delega_accesso_telematico_planimetrie_agenti_immobiliari.pdf")
OPENAPI_DELEGA_URL = "https://docs.openapi.it/docuengine/delega_catasto.pdf"
CONSULTAZIONE_PERSONALE_URL = "https://www.agenziaentrate.gov.it/portale/consultazione-personale"


class Unit(BaseModel):
    foglio: str = Field(pattern=r"^\d{1,5}$")
    particella: str = Field(pattern=r"^\d{1,6}$")
    subalterno: str | None = Field(default=None, pattern=r"^\d{0,5}$")
    id_immobile: str | None = Field(default=None, max_length=300)


class Purchase(BaseModel):
    confirm_cost_eur: float
    unit: Unit | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client() -> CatastoClient:
    if not openapi_catasto.configured():
        raise HTTPException(503, "Servizio Catasto non attivo: inserisci OPENAPI_CATASTO_TOKEN nel file .env del backend.")
    return CatastoClient()


def _checks(client, property_id: int) -> list[dict]:
    try:
        return (client.table("property_registry_checks").select("*").eq("property_id", property_id)
                .order("created_at", desc=True).execute().data or [])
    except Exception:
        return []


def _record(client, row: dict) -> dict:
    try:
        return client.table("property_registry_checks").insert(row).execute().data[0]
    except Exception as exc:
        raise HTTPException(502, "Unable to record the registry request") from exc


def _update(client, check_id: str, changes: dict) -> None:
    try:
        client.table("property_registry_checks").update({**changes, "updated_at": _now()}).eq("id", check_id).execute()
    except Exception:
        pass


def _same_unit(check: dict, unit: Unit | None) -> bool:
    params = check.get("params") or {}
    return unit is not None and (params.get("foglio"), params.get("particella"), params.get("subalterno") or None) == \
        (unit.foglio, unit.particella, unit.subalterno or None)


def _location(client, property_id: int) -> tuple[dict, dict]:
    """(property, istat comune row) of the property, geocoded if needed."""
    record = _located(client, property_id, get_property(property_id, client))
    zone = _zone(client, record)
    comune = None
    if zone and zone.get("comune_cat"):
        try:
            comune = (client.table("istat_comuni").select("*").eq("codice_catastale", zone["comune_cat"]).limit(1)
                      .execute().data or [None])[0]
        except Exception:
            comune = None
    if not comune:
        raise HTTPException(409, "Posizione non trovata: controlla indirizzo e comune nella scheda")
    return record, comune


def _save_document(client, *, property_id: int, document_type: str, file_name: str, fields: dict,
                   content: bytes | None = None, media_type: str | None = None) -> dict:
    """Insert a document built from registry data, with its analysis row and facts."""
    raw = content or json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()
    now = _now()
    document = _insert_one(client, "documents", {
        "agente_id": client.smartbuy_user_id, "fascicolo_id": str(property_id),
        "content_sha256": hashlib.sha256(raw).hexdigest(), "file_name": file_name, "document_type": document_type,
        "processing_status": "completed", "source_type": "openapi_catasto", "extracted_fields": fields,
        "red_flags": [], "consistency_discrepancies": [], "ocr_confidence": 1.0, "extraction_confidence": 1.0,
        "confidence_score": 1.0, "processed_at": now, "processing_time_seconds": 0,
    })
    analysis = _insert_one(client, "document_analyses", {
        "property_id": property_id, "document_id": document["id"], "document_name": file_name,
        "document_type": document_type, "confidence_score": 1.0, "analysis_status": "completed",
        "extracted_data": fields, "warnings": [], "analyzed_at": now,
    })
    if content:
        store_original(client, property_id=property_id, document_id=document["id"], filename=file_name,
                       content=content, media_type=media_type)
    persist_document_facts(client, property_id=property_id, document=document, analysis=analysis, extracted_fields=fields,
                           default_confidence=1.0, model_name="openapi_catasto")
    return document


@router.get("/properties/{property_id}/registry")
def registry_status(property_id: int, client=Depends(user_client)):
    record = get_property(property_id, client)
    checks = _checks(client, property_id)
    if openapi_catasto.configured():
        for check in checks:
            if check["status"] == "pending" and check.get("request_id"):
                _finish_pending(client, property_id, check)
        checks = _checks(client, property_id)
    return {"configured": openapi_catasto.configured(), "environment": openapi_catasto.environment(),
            "prices_eur": registry.PRICES_EUR, "checks": checks, "source": registry.SOURCE,
            "ape_lookup_url": APE_LOOKUP_URL, "planimetria_delega_url": PLANIMETRIA_DELEGA_URL,
            "openapi_delega_url": OPENAPI_DELEGA_URL, "consultazione_personale_url": CONSULTAZIONE_PERSONALE_URL,
            "delega_confirmed_at": record.get("delega_confirmed_at"),
            "planimetria_delega_sent_at": record.get("planimetria_delega_sent_at"),
            "spent_eur": round(sum(float(c.get("cost_eur") or 0) for c in checks if c["status"] == "done"), 2)}


class DelegaConfirmation(BaseModel):
    confirmed: bool


@router.post("/properties/{property_id}/registry/delega")
def confirm_delega(property_id: int, payload: DelegaConfirmation, client=Depends(user_client)):
    """Agent's statement that they hold a delega/incarico from the owner to request these data.

    This does not itself grant any legal right: it only unlocks the flow in
    the app, and the actual signed delega (see the PDF modules) must exist.
    """
    get_property(property_id, client)
    value = _now() if payload.confirmed else None
    try:
        response = client.table("properties").update({"delega_confirmed_at": value}).eq("id", property_id).execute()
    except Exception as exc:
        raise HTTPException(502, "Unable to update the delega") from exc
    return {"delega_confirmed_at": (response.data or [{}])[0].get("delega_confirmed_at")}


class PlanimetriaDelegaTracking(BaseModel):
    sent: bool


@router.post("/properties/{property_id}/registry/planimetria-delega")
def track_planimetria_delega(property_id: int, payload: PlanimetriaDelegaTracking, client=Depends(user_client)):
    """Agent's note that the signed Mod. 12T-AgIm was sent to Agenzia delle Entrate.

    Purely informational reminder of the 30-day submission deadline from the
    owner's signature; unlike delega_confirmed_at it gates nothing, since the
    planimetria itself never flows through this app's API.
    """
    get_property(property_id, client)
    value = _now() if payload.sent else None
    try:
        response = client.table("properties").update({"planimetria_delega_sent_at": value}).eq("id", property_id).execute()
    except Exception as exc:
        raise HTTPException(502, "Unable to update the planimetria delega tracking") from exc
    return {"planimetria_delega_sent_at": (response.data or [{}])[0].get("planimetria_delega_sent_at")}


def _require_delega(client, property_id: int) -> None:
    record = get_property(property_id, client)
    if not record.get("delega_confirmed_at"):
        raise HTTPException(409, "Conferma prima di avere la delega o l'incarico del proprietario per richiedere questi dati "
                                 "(sezione Deleghe).")


def _require_confirmation(kind: str, payload: Purchase) -> float:
    price = registry.PRICES_EUR[kind]
    if abs(payload.confirm_cost_eur - price) > 0.001:
        raise HTTPException(409, f"Conferma il costo di {price:.2f} € + IVA per procedere")
    return price


@router.post("/properties/{property_id}/registry/immobili", status_code=201)
def find_units(property_id: int, payload: Purchase, client=Depends(user_client)):
    """Cadastral units at the property's address (street and house number)."""
    record, comune = _location(client, property_id)
    done = next((c for c in _checks(client, property_id) if c["kind"] == "immobili" and c["status"] == "done"), None)
    if done:
        return done
    _require_delega(client, property_id)
    price = _require_confirmation("immobili", payload)
    catasto = _client()
    street, number = registry.split_address(record.get("address") or "")
    row = {"property_id": property_id, "kind": "immobili", "environment": catasto.environment, "status": "done",
           "params": {"civico": number, "via": street}, "cost_eur": price}
    try:
        candidate = registry.pick_address(catasto.search_address(comune["sigla_provincia"], comune["nome"].upper(), street), street)
        if not candidate:
            raise HTTPException(404, f"Via '{street}' non trovata nello stradario catastale di {comune['nome']}: controlla l'indirizzo")
        row["params"] = {**row["params"], "id_indirizzo": candidate["id_indirizzo"], "indirizzo": candidate.get("indirizzo")}
        result = catasto.units_at_address(candidate["id_indirizzo"], number)
        return _record(client, {**row, "request_id": result.get("id"), "result": {"units": registry.units(result)}})
    except OpenapiPending as pending:
        return _record(client, {**row, "status": "pending", "request_id": pending.request_id})
    except OpenapiError as exc:
        raise HTTPException(502, f"Catasto: {exc}") from exc


@router.post("/properties/{property_id}/registry/prospetto", status_code=201)
def owners(property_id: int, payload: Purchase, client=Depends(user_client)):
    """Owners, shares, category and rent of one unit, saved as a visura document."""
    if not payload.unit:
        raise HTTPException(422, "Indica foglio, particella e subalterno")
    record, comune = _location(client, property_id)
    done = next((c for c in _checks(client, property_id) if c["kind"] == "prospetto" and c["status"] == "done"
                 and _same_unit(c, payload.unit)), None)
    if done:
        return done
    _require_delega(client, property_id)
    price = _require_confirmation("prospetto", payload)
    catasto = _client()
    unit = payload.unit
    row = {"property_id": property_id, "kind": "prospetto", "environment": catasto.environment, "status": "done",
           "params": unit.model_dump(), "cost_eur": price}
    try:
        result = catasto.prospetto(provincia=comune["sigla_provincia"], comune=comune["nome"].upper(), foglio=unit.foglio,
                                   particella=unit.particella, subalterno=unit.subalterno)
    except OpenapiPending as pending:
        return _record(client, {**row, "status": "pending", "request_id": pending.request_id})
    except OpenapiError as exc:
        raise HTTPException(502, f"Catasto: {exc}") from exc
    return _finish_prospetto(client, property_id, comune, row, result)


def _finish_prospetto(client, property_id: int, comune: dict, row: dict, result: dict) -> dict:
    fields, owner_list = registry.visura_fields(result, comune["nome"])
    document = None
    if fields:
        unit = row["params"]
        document = _save_document(client, property_id=property_id, document_type="visura_catastale",
                                  file_name=f"Prospetto catastale Fg.{unit['foglio']} Part.{unit['particella']}"
                                            f"{' Sub.' + unit['subalterno'] if unit.get('subalterno') else ''} (Catasto).json",
                                  fields=fields)
    payload = {**row, "request_id": result.get("id"), "result": {"owners": owner_list, "fields": fields},
               "document_id": document["id"] if document else None}
    if row.get("id"):
        _update(client, row["id"], {k: v for k, v in payload.items() if k not in {"id", "property_id"}})
        return {**row, **payload}
    return _record(client, payload)


@router.post("/properties/{property_id}/registry/visura-pdf", status_code=201)
def official_visura(property_id: int, payload: Purchase, client=Depends(user_client)):
    """Official visura PDF of a unit, attached to the property's documents."""
    if not payload.unit or not payload.unit.id_immobile:
        raise HTTPException(422, "Prima cerca gli immobili all'indirizzo: serve l'identificativo dell'immobile")
    get_property(property_id, client)
    done = next((c for c in _checks(client, property_id) if c["kind"] == "visura_pdf" and c["status"] == "done"
                 and _same_unit(c, payload.unit)), None)
    if done:
        return done
    _require_delega(client, property_id)
    price = _require_confirmation("visura_pdf", payload)
    catasto = _client()
    row = {"property_id": property_id, "kind": "visura_pdf", "environment": catasto.environment, "status": "done",
           "params": payload.unit.model_dump(), "cost_eur": price}
    try:
        data, pdf = catasto.visura_pdf(payload.unit.id_immobile)
    except OpenapiPending as pending:
        return _record(client, {**row, "status": "pending", "request_id": pending.request_id})
    except OpenapiError as exc:
        raise HTTPException(502, f"Catasto: {exc}") from exc
    return _finish_visura(client, property_id, {**row, "request_id": data.get("id")}, pdf)


def _finish_visura(client, property_id: int, row: dict, pdf: bytes) -> dict:
    unit = row["params"]
    prospetto = next((c for c in _checks(client, property_id) if c["kind"] == "prospetto" and c["status"] == "done"
                      and (c.get("params") or {}).get("foglio") == unit["foglio"]
                      and (c.get("params") or {}).get("particella") == unit["particella"]
                      and ((c.get("params") or {}).get("subalterno") or None) == (unit.get("subalterno") or None)), None)
    fields = ((prospetto or {}).get("result") or {}).get("fields") or {"note_incertezza": ["Dati da leggere dal PDF"]}
    document = _save_document(client, property_id=property_id, document_type="visura_catastale",
                              file_name=f"Visura catastale Fg.{unit['foglio']} Part.{unit['particella']}.pdf",
                              fields=fields, content=pdf, media_type="application/pdf")
    payload = {**row, "status": "done", "document_id": document["id"], "result": {"pdf": True}}
    if row.get("id"):
        _update(client, row["id"], {k: v for k, v in payload.items() if k not in {"id", "property_id"}})
        return payload
    return _record(client, payload)


@router.post("/properties/{property_id}/registry/ispezione", status_code=201)
def mortgage_inspection(property_id: int, payload: Purchase, client=Depends(user_client)):
    """Land-registry notes on one unit (ipoteche, pignoramenti, provenienza)."""
    if not payload.unit:
        raise HTTPException(422, "Indica foglio, particella e subalterno")
    record, comune = _location(client, property_id)
    done = next((c for c in _checks(client, property_id) if c["kind"] == "ispezione" and c["status"] == "done"
                 and _same_unit(c, payload.unit)), None)
    if done:
        return done
    _require_delega(client, property_id)
    price = _require_confirmation("ispezione", payload)
    catasto = _client()
    unit = payload.unit
    row = {"property_id": property_id, "kind": "ispezione", "environment": catasto.environment, "status": "done",
           "params": unit.model_dump(), "cost_eur": price}
    try:
        conservatoria = catasto.conservatoria_for(comune["codice_catastale"], (comune["nome"], comune.get("sigla_provincia")))
        if not conservatoria:
            raise HTTPException(404, f"Conservatoria di {comune['nome']} non trovata")
        row["params"] = {**row["params"], "conservatoria": conservatoria}
        result = catasto.mortgage_notes(conservatoria=conservatoria, comune=comune["nome"].upper(), foglio=unit.foglio,
                                        particella=unit.particella, subalterno=unit.subalterno)
    except OpenapiPending as pending:
        return _record(client, {**row, "status": "pending", "request_id": pending.request_id})
    except OpenapiError as exc:
        raise HTTPException(502, f"Conservatoria: {exc}") from exc
    return _finish_inspection(client, property_id, comune, row, result)


def _finish_inspection(client, property_id: int, comune: dict, row: dict, result: dict) -> dict:
    summary = registry.mortgage_summary(result)
    unit = row["params"]
    riferimento = {"comune": comune["nome"], "foglio": unit["foglio"], "particella": unit["particella"],
                   "subalterno": unit.get("subalterno") or None}
    document = _save_document(client, property_id=property_id, document_type="visura_ipotecaria",
                              file_name=f"Ispezione ipotecaria Fg.{unit['foglio']} Part.{unit['particella']} (Conservatoria).json",
                              fields=registry.mortgage_fields(summary, riferimento))
    payload = {**row, "request_id": result.get("id"), "result": summary, "document_id": document["id"]}
    if row.get("id"):
        _update(client, row["id"], {k: v for k, v in payload.items() if k not in {"id", "property_id"}})
        return {**row, **payload}
    return _record(client, payload)


def _finish_pending(client, property_id: int, check: dict) -> None:
    """Complete a request that was still running when it was bought."""
    try:
        catasto = CatastoClient(wait_seconds=0)
        result = catasto.resume(check["kind"], check["request_id"])
        if check["kind"] == "visura_pdf":
            _finish_visura(client, property_id, {**check, "status": "done"}, catasto.download_visura(check["request_id"]))
            return
    except OpenapiPending:
        return
    except OpenapiError as exc:
        _update(client, check["id"], {"status": "error", "error": str(exc)})
        return
    row = {**check, "status": "done"}
    if check["kind"] == "immobili":
        _update(client, check["id"], {"status": "done", "result": {"units": registry.units(result)}})
    elif check["kind"] in {"prospetto", "ispezione"}:
        _, comune = _location(client, property_id)
        (_finish_prospetto if check["kind"] == "prospetto" else _finish_inspection)(client, property_id, comune, row, result)
