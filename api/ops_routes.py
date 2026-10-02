"""Maintenance endpoints called by an automation (n8n), not by users.

Protected by a shared secret in X-SmartBuy-Ops-Token (SMARTBUY_OPS_SECRET); unset secret
disables them. They use the privileged client, so they only ever report counts and index
documents — no document content leaves through them.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException

router = APIRouter(prefix="/ops", tags=["ops"])


def require_ops(x_smartbuy_ops_token: str | None = Header(default=None)) -> None:
    secret = os.getenv("SMARTBUY_OPS_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Ops endpoints not configured")
    if not x_smartbuy_ops_token or not secrets.compare_digest(x_smartbuy_ops_token, secret):
        raise HTTPException(status_code=403, detail="Forbidden")


def _admin():
    from integrations.supabase.client import supabase
    return supabase


def rag_health(client) -> dict:
    """How far the chunk index is behind the stored document text."""
    indexed = {r["document_id"] for r in (client.table("document_chunks").select("document_id").execute().data or [])}
    texts = client.table("document_text_extractions").select("document_id,raw_text").execute().data or []
    waiting = [t["document_id"] for t in texts if t.get("raw_text") and t["document_id"] not in indexed]
    return {"documents_with_text": len(texts), "documents_indexed": len(indexed), "backlog": len(waiting)}


@router.get("/rag/health", dependencies=[Depends(require_ops)])
def rag_health_route():
    return rag_health(_admin())


@router.post("/rag/backfill", dependencies=[Depends(require_ops)])
def rag_backfill_route(limit: int = 50):
    from document_engine.rag_service import backfill_missing
    client = _admin()
    result = backfill_missing(client, limit=max(1, min(limit, 200)))
    return {**result, **rag_health(client)}
