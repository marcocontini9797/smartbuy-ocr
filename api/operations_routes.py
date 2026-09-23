"""Operational APIs for source routing, GIS, requests and cross validation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.property_routes import _rows, get_property
from api.session import user_client
from core.operational_models import DocumentRequest
from document_engine.checklist import build_checklist
from document_engine.negotiation import build_negotiation_brief
from document_engine.cross_validation import cross_validate, summarize
from document_engine.operational_services import route_ape_source, validate_gis
from document_engine.external_sources import REGISTRY, source_plan
from document_engine.acquisition_engine import build_acquisition_plan


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
        raise HTTPException(502, "Cross-validation sources unavailable") from exc
    return property_record, facts, documents, {str(row["id"]): row for row in provenance}


def _findings(property_id: int, client):
    property_record, facts, documents, provenance = _validation_sources(property_id, client)
    findings = cross_validate(property_id, facts=facts, documents=documents, provenance=provenance,
                              property_record=property_record)
    return property_record, documents, findings, facts


@router.get("/properties/{property_id}/cross-validation")
def cross_validation(property_id: int, client=Depends(user_client)):
    _, _, findings, _ = _findings(property_id, client)
    return {
        "property_id": property_id,
        "findings": [item.model_dump(mode="json") for item in findings],
        "summary": summarize(findings),
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
        raise HTTPException(502, "Document service unavailable") from exc
    return build_acquisition_plan(
        property_record=prop,
        documents=documents,
        facts=_rows(client, "property_facts", property_id),
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


@router.get("/properties/{property_id}/document-packages")
def document_packages(property_id: int, client=Depends(user_client)):
    from document_engine.document_acquisition import build_document_packages
    prop = get_property(property_id, client)
    analyses = _rows(client, "document_analyses", property_id)
    ids = list({r["document_id"] for r in analyses if r.get("document_id") is not None})
    try:
        documents = client.table("documents").select("*").in_("id", ids).execute().data or [] if ids else []
    except Exception as exc:
        raise HTTPException(502, "Document service unavailable") from exc
    return build_document_packages(prop, documents, _rows(client, "smartbuy_document_requests", property_id))


@router.post("/properties/{property_id}/document-packages/prepare")
def prepare_document_packages(property_id: int, client=Depends(user_client)):
    from document_engine.document_acquisition import persist_request_drafts
    plan = document_packages(property_id, client)
    try:
        result = persist_request_drafts(client, plan)
    except Exception as exc:
        raise HTTPException(502, "Unable to persist document requests; retry safely") from exc
    return {**result, "plan": document_packages(property_id, client)}
