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


@router.get("/feedback/negative", dependencies=[Depends(require_ops)])
def negative_feedback(days: int = 7):
    """Answers agents marked as wrong in the last `days` days, for the weekly review. Contains
    questions and answers, so it stays behind the ops secret."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))).isoformat()
    rows = (_admin().table("agent_answer_feedback").select("property_id,question,answer,comment,grounded,sources,created_at")
            .eq("rating", -1).gte("created_at", since).order("created_at", desc=True).limit(100).execute().data or [])
    return {"count": len(rows), "items": rows}


@router.get("/rag/calibration", dependencies=[Depends(require_ops)])
def rag_calibration(days: int = 90):
    """Where the retrieval thresholds should sit according to what agents rated. Counts and
    numbers only: no question or answer text."""
    from datetime import datetime, timedelta, timezone

    from document_engine.rag_calibration import calibration_report
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))).isoformat()
    client = _admin()
    feedback = (client.table("agent_answer_feedback").select("trace_id,rating").gte("created_at", since)
                .not_.is_("trace_id", "null").limit(5000).execute().data or [])
    traces = {t["id"]: t for t in (client.table("agent_retrieval_traces").select("id,strength,best_relevance")
                                   .in_("id", [f["trace_id"] for f in feedback][:1000] or ["00000000-0000-0000-0000-000000000000"])
                                   .execute().data or [])}
    rows = [{"rating": f["rating"], **{k: traces[f["trace_id"]][k] for k in ("strength", "best_relevance")}}
            for f in feedback if f["trace_id"] in traces]
    return calibration_report(rows)



@router.post("/rag/learn", dependencies=[Depends(require_ops)])
def rag_learn(tune: bool = True):
    """One learning cycle: vet new ratings, maybe adopt better parameters, roll back if worse."""
    from document_engine.rag_learning import run_cycle
    from document_engine.rag_llm import judge_support
    return run_cycle(_admin(), judge_support, tune=tune)


@router.get("/rag/config", dependencies=[Depends(require_ops)])
def rag_config_history():
    """The configuration history with the reason and the numbers behind every change."""
    rows = (_admin().table("rag_configs").select("id,status,params,parent_id,reason,metrics,created_at,activated_at")
            .order("id", desc=True).limit(20).execute().data or [])
    return {"versions": rows}
