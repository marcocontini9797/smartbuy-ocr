"""Read-only, unauthenticated fascicolo sharing: an agent generates a link a
buyer can open without an account, to do their own due diligence (checklist,
risks, documents) without depending on the agent for every question.

Every endpoint here takes the share token, never a session. Authorization is
the token itself (unguessable, revocable) plus the property's share_enabled
flag, enforced inside the SECURITY DEFINER Postgres functions in
sql/024_property_share.sql — not by RLS, which requires auth.uid() and an
anonymous visitor never has one.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client

from document_engine.agent_llm_gateway import AgentLLMGateway
from document_engine.agent_retrieval_supabase import build_agent_context
from document_engine.checklist import build_checklist
from document_engine.superseded import drop_superseded
from document_engine.cross_validation import cross_validate
from api.intelligence_service import build_property_intelligence

router = APIRouter(prefix="/api/v1", tags=["share"])
DOCUMENT_BUCKET = "smartbuy-documents"


class SharedAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


def _anon_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise HTTPException(503, "Condivisione non configurata")
    return create_client(url, key)


def _fetch_shared(token: str) -> dict:
    if not token or len(token) < 16:
        raise HTTPException(404, "Fascicolo non trovato o non più condiviso")
    client = _anon_client()
    try:
        data = client.rpc("smartbuy_shared_fascicolo", {"p_token": token}).execute().data
    except Exception as exc:
        raise HTTPException(502, "Servizio non raggiungibile") from exc
    if not data:
        raise HTTPException(404, "Fascicolo non trovato o non più condiviso")
    return data


@router.get("/shared/{token}")
def shared_fascicolo(token: str):
    data = _fetch_shared(token)
    property_record = data["property"]
    documents, facts = drop_superseded(data["documents"], data["facts"])
    analyses = data["analyses"]
    provenance = data["provenance"]

    try:
        provenance_by_id = {str(row["id"]): row for row in provenance if row.get("id") is not None}
        findings = cross_validate(property_record["id"], facts=facts, documents=documents,
                                  provenance=provenance_by_id, property_record=property_record)
        checklist = build_checklist(property_record=property_record, documents=documents,
                                    findings=findings, facts=facts)
        intelligence = build_property_intelligence(property_record=property_record, facts=facts,
                                                    documents=documents, analyses=analyses, provenance=provenance)
    except Exception as exc:
        raise HTTPException(502, "Impossibile preparare il fascicolo") from exc

    return {
        "property": {
            "address": property_record.get("address"), "city": property_record.get("city"),
            "surface_m2": property_record.get("surface_m2"), "asking_price": property_record.get("asking_price"),
            "typology": property_record.get("typology"), "contract": property_record.get("contract"),
        },
        "checklist": checklist,
        "readiness": intelligence.get("summary"),
        "risks": intelligence.get("risks"),
        "gaps": intelligence.get("gaps"),
        "documents": [
            {"id": d.get("id"), "file_name": d.get("file_name"), "document_type": d.get("document_type"),
             "processing_status": d.get("processing_status"), "has_original": bool(d.get("content_sha256"))}
            for d in documents
        ],
    }


@router.post("/shared/{token}/ask")
def shared_ask(token: str, payload: SharedAskRequest):
    data = _fetch_shared(token)
    property_record = data["property"]
    context = build_agent_context(property_id=property_record["id"], question=payload.question,
                                  facts=data["facts"], documents=data["documents"], provenance=data["provenance"])
    try:
        response = AgentLLMGateway().complete(task="property_analysis", context=context,
                                              property_id=property_record["id"], user_query=payload.question)
    except Exception as exc:
        raise HTTPException(502, "L'assistente non è riuscito a rispondere: riprova tra poco.") from exc
    return {"answer": response.answer, "confidence": response.confidence,
            "grounded": response.metadata.get("grounded", True),
            "sources": getattr(response, "sources", None) or context.get("sources", [])}


@router.get("/shared/{token}/documents/{document_id}/file")
def shared_document_file(token: str, document_id: int):
    if not token or len(token) < 16:
        raise HTTPException(404, "Documento non disponibile")
    client = _anon_client()
    try:
        path = client.rpc("smartbuy_shared_document_path", {"p_token": token, "p_document_id": document_id}).execute().data
    except Exception as exc:
        raise HTTPException(502, "Servizio non raggiungibile") from exc
    if not path:
        raise HTTPException(404, "Documento non disponibile")
    from integrations.supabase.client import supabase as service_client
    try:
        signed = service_client.storage.from_(DOCUMENT_BUCKET).create_signed_url(path, 300)
    except Exception as exc:
        raise HTTPException(502, "Impossibile aprire il documento") from exc
    url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
    if not url:
        raise HTTPException(502, "Impossibile aprire il documento")
    return {"url": url, "expires_in": 300}
