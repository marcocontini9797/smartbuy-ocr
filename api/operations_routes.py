"""Operational APIs for source routing, GIS, requests and cross validation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.property_routes import _optional_rows, _rows, get_property
from api.session import user_client
from core.operational_models import DocumentRequest
from document_engine.checklist import build_checklist
from document_engine.negotiation import build_negotiation_brief
from document_engine.cross_validation import cross_validate, summarize
from document_engine.agent_review import build_agent_review
from document_engine.operational_services import route_ape_source, validate_gis
from document_engine.external_sources import REGISTRY, source_plan
from document_engine.acquisition_engine import build_acquisition_plan
from document_engine.superseded import current_documents, drop_superseded


router = APIRouter(prefix="/api/v1", tags=["operations"])


@router.get("/external-sources")
def external_sources():
    return {"sources": [item.model_dump(mode="json") for item in REGISTRY.values()]}


class DocumentRequestInput(BaseModel):
    document_type: str
    requested_from: str
    reason: str
    legal_basis: str | None = None


@router.get("/properties/{property_id}/verification-plan")
def verification_plan(property_id: int, client=Depends(user_client)):
    prop = get_property(property_id, client)
    province = prop.get("province") or prop.get("provincia")
    available_inputs = {
        name for name, value in {
            "latitude": prop.get("latitude"), "longitude": prop.get("longitude"),
            "ape_code": prop.get("ape_code"), "comune_catastale": prop.get("comune_catastale"),
            "foglio": prop.get("foglio"), "mappale": prop.get("mappale") or prop.get("particella"),
            "particella": prop.get("particella") or prop.get("mappale"), "subalterno": prop.get("subalterno"),
        }.items() if value not in (None, "")
    }
    return {
        "property_id": property_id,
        "ape": route_ape_source(province=province),
        "gis": validate_gis(
            latitude=prop.get("latitude"), longitude=prop.get("longitude"),
            expected_city=prop.get("city") or prop.get("comune"),
        ),
        "source_plan": source_plan(province=province, available_inputs=available_inputs),
    }


def _validation_sources(property_id: int, client):
    """Property, facts, documents and provenance used by checks and checklist."""
    property_record = get_property(property_id, client)
    facts = _rows(client, "property_facts", property_id)
    analyses = _rows(client, "document_analyses", property_id)
    document_ids = list({row["document_id"] for row in analyses if row.get("document_id") is not None})
    provenance_ids = list({row["provenance_id"] for row in facts if row.get("provenance_id") is not None})
    try:
        documents = client.table("documents").select("*").in_("id", document_ids).execute().data or [] if document_ids else []
        provenance = client.table("fact_provenance").select("*").in_("id", provenance_ids).execute().data or [] if provenance_ids else []
    except Exception as exc:
        raise HTTPException(502, "Non riesco a leggere i dati per le verifiche incrociate: riprova tra poco.") from exc
    documents, facts = drop_superseded(documents, facts)
    return property_record, facts, documents, {str(row["id"]): row for row in provenance}


def _findings(property_id: int, client):
    property_record, facts, documents, provenance = _validation_sources(property_id, client)
    facts = [{**f, "provenance": provenance.get(str(f.get("provenance_id"))) or f.get("provenance") or {},
              "source_document_id": f.get("source_document_id") or
                  (provenance.get(str(f.get("provenance_id"))) or f.get("provenance") or {}).get("document_id")} for f in facts]
    findings = cross_validate(property_id, facts=facts, documents=documents, provenance=provenance,
                              property_record=property_record)
    return property_record, documents, findings, facts


@router.get("/properties/{property_id}/cross-validation")
def cross_validation(property_id: int, client=Depends(user_client)):
    property_record, documents, findings, facts = _findings(property_id, client)
    return {
        "property_id": property_id,
        "findings": [item.model_dump(mode="json") for item in findings],
        "summary": summarize(findings),
        "agent_review": build_agent_review(property_id,property_record,documents,findings,facts),
    }


@router.get("/properties/{property_id}/checklist")
def sale_checklist(property_id: int, client=Depends(user_client)):
    property_record, documents, findings, facts = _findings(property_id, client)
    return {"property_id": property_id,
            **build_checklist(property_record=property_record, documents=documents, findings=findings, facts=facts)}


@router.get("/properties/{property_id}/negotiation")
def negotiation_brief(property_id: int, client=Depends(user_client)):
    property_record, documents, findings, facts = _findings(property_id, client)
    checklist = build_checklist(property_record=property_record, documents=documents, findings=findings, facts=facts)
    return {"property_id": property_id, "verdict": checklist["summary"]["verdict"], **build_negotiation_brief(checklist)}


@router.get("/properties/{property_id}/acquisition-plan")
def acquisition_plan(property_id: int, client=Depends(user_client)):
    prop = get_property(property_id, client)
    analyses = _rows(client, "document_analyses", property_id)
    document_ids = list({row["document_id"] for row in analyses if row.get("document_id") is not None})
    try:
        documents = client.table("documents").select("*").in_("id", document_ids).execute().data or [] if document_ids else []
    except Exception as exc:
        raise HTTPException(502, "Non riesco a leggere i documenti in questo momento: riprova tra poco.") from exc
    documents, facts = drop_superseded(documents, _rows(client, "property_facts", property_id))
    return build_acquisition_plan(
        property_record=prop,
        documents=documents,
        facts=facts,
        existing_requests=_rows(client, "smartbuy_document_requests", property_id),
    )


@router.get("/properties/{property_id}/document-requests")
def list_document_requests(property_id: int, client=Depends(user_client)):
    get_property(property_id, client)
    return {"property_id": property_id, "requests": _rows(client, "smartbuy_document_requests", property_id)}


@router.post("/properties/{property_id}/document-requests", status_code=201)
def create_document_request(property_id: int, payload: DocumentRequestInput, client=Depends(user_client)):
    get_property(property_id, client)
    request = DocumentRequest.create(property_id=property_id, **payload.model_dump())
    result = client.table("smartbuy_document_requests").upsert(
        request.model_dump(mode="json"), on_conflict="request_id"
    ).execute()
    return (result.data or [request.model_dump(mode="json")])[0]


def _document_packages_plan(property_id: int, client) -> tuple[dict, dict]:
    from document_engine.document_acquisition import build_document_packages
    prop = get_property(property_id, client)
    analyses = _rows(client, "document_analyses", property_id)
    ids = list({r["document_id"] for r in analyses if r.get("document_id") is not None})
    try:
        documents = client.table("documents").select("*").in_("id", ids).execute().data or [] if ids else []
    except Exception as exc:
        raise HTTPException(502, "Non riesco a leggere i documenti in questo momento: riprova tra poco.") from exc
    plan = build_document_packages(prop, current_documents(documents), _rows(client, "smartbuy_document_requests", property_id))
    return plan, prop


@router.get("/properties/{property_id}/document-packages")
def document_packages(property_id: int, client=Depends(user_client)):
    from document_engine.document_acquisition import apply_request_messages
    plan, prop = _document_packages_plan(property_id, client)
    # Read-only: serves whatever letter is already cached, never calls the AI here.
    plan, _ = apply_request_messages(plan, prop, _optional_rows(client, "smartbuy_request_messages", property_id), generate=False)
    return plan


@router.post("/properties/{property_id}/document-packages/prepare")
def prepare_document_packages(property_id: int, client=Depends(user_client)):
    from document_engine.document_acquisition import apply_request_messages, persist_request_drafts
    plan, prop = _document_packages_plan(property_id, client)
    try:
        result = persist_request_drafts(client, plan)
    except Exception as exc:
        raise HTTPException(502, "Le richieste non sono state salvate: puoi riprovare senza rischi.") from exc
    plan, _ = _document_packages_plan(property_id, client)
    plan, to_persist = apply_request_messages(
        plan, prop, _optional_rows(client, "smartbuy_request_messages", property_id), generate=True)
    if to_persist:
        try:
            client.table("smartbuy_request_messages").upsert(
                to_persist, on_conflict="property_id,recipient_role").execute()
        except Exception:
            pass  # composed letters still returned in `plan`; just not cached for next time
    return {**result, "plan": plan}


@router.get("/properties-overview")
def properties_overview(client=Depends(user_client)):
    """One line of status per property, for the list: how many documents, what is missing, what is wrong.

    Read in bulk (three queries for the whole portfolio, not three per property) and computed with the same
    checklist engine as the detail page, so the list never disagrees with the property it links to.
    Cross-validation findings are left out (they need provenance reads per property); the detail page adds them."""
    from concurrent.futures import ThreadPoolExecutor

    try:
        properties = (client.table("properties").select("*").eq("user_id", client.smartbuy_user_id)
                      .order("id", desc=True).limit(200).execute().data or [])
    except Exception as exc:
        raise HTTPException(502, "Non riesco a leggere i dati in questo momento: riprova tra poco.") from exc
    ids = [p["id"] for p in properties]
    if not ids:
        return {"items": []}

    def read(table: str) -> list[dict]:
        try:
            return client.table(table).select("*").in_("property_id", ids).execute().data or []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        analyses_f, facts_f = pool.submit(read, "document_analyses"), pool.submit(read, "property_facts")
        analyses, facts = analyses_f.result(), facts_f.result()
    document_ids = list({row["document_id"] for row in analyses if row.get("document_id") is not None})
    try:
        documents = client.table("documents").select("*").in_("id", document_ids).execute().data or [] if document_ids else []
    except Exception as exc:
        raise HTTPException(502, "Non riesco a leggere i documenti in questo momento: riprova tra poco.") from exc
    by_id = {str(d["id"]): d for d in documents}

    items = []
    for prop in properties:
        mine = {str(a["document_id"]) for a in analyses if str(a.get("property_id")) == str(prop["id"]) and a.get("document_id") is not None}
        prop_docs, prop_facts = drop_superseded([by_id[i] for i in mine if i in by_id],
                                                [f for f in facts if str(f.get("property_id")) == str(prop["id"])])
        try:
            summary = build_checklist(property_record=prop, documents=prop_docs, findings=[], facts=prop_facts)["summary"]
        except Exception:
            items.append({"property_id": prop["id"], "documents": len(prop_docs), "status": None})
            continue
        items.append({"property_id": prop["id"], "documents": len(prop_docs), "required_total": summary["required_total"],
                      "required_present": summary["required_present"], "missing_required": summary["missing_required"],
                      "problems": summary["problems"], "to_check": summary["to_check"], "tone": summary["tone"]})
    return {"items": items}
