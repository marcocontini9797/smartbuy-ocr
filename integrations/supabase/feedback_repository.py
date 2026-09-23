"""Supabase persistence adapter for FeedbackService.

All multi-record writes go through a Postgres RPC to preserve atomicity.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from core.feedback_models import FeedbackEvent, FeedbackSignal, FeedbackTarget
from .client import supabase


_TARGET_TABLES = {
    FeedbackTarget.FACT: "property_facts",
    FeedbackTarget.EVIDENCE: "fact_provenance",
    FeedbackTarget.DOCUMENT: "documents",
}


class SupabaseFeedbackRepository:
    def __init__(self, client=None) -> None:
        self.client = client or supabase

    def load_target(self, event: FeedbackEvent) -> dict[str, Any] | None:
        table = _TARGET_TABLES.get(event.target_type)
        if table is None:
            # ISSUE/MISSING/RAG need canonical tables from the Fiverr contract.
            # They are deliberately rejected instead of trusting a client payload.
            return None
        query = self.client.table(table).select("*").eq("id", event.target_id)
        if event.target_type == FeedbackTarget.DOCUMENT:
            # documents is linked through document_analyses in the real schema.
            linked = (
                self.client.table("document_analyses").select("id")
                .eq("document_id", event.target_id)
                .eq("property_id", event.property_id).limit(1).execute()
            )
            if not linked.data:
                return None
        else:
            query = query.eq("property_id", event.property_id)
        response = query.limit(1).execute()
        if not response.data:
            return None
        row = response.data[0]
        payload = _canonical_payload(event.target_type, row)
        version = row.get("updated_at") or sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return {
            "id": str(row["id"]),
            "version": str(version),
            "payload": payload,
        }

    def ingest_atomic(self, event: FeedbackEvent, signal: FeedbackSignal,
                      recalculation_stages: list[str]) -> dict[str, Any]:
        response = self.client.rpc("smartbuy_ingest_feedback", {
            "p_event": event.model_dump(mode="json"),
            "p_signal": signal.model_dump(mode="json"),
            "p_command_hash": event.command_hash(),
            "p_recalculation_stages": recalculation_stages,
        }).execute()
        return response.data


def _canonical_payload(target_type: FeedbackTarget, row: dict[str, Any]) -> dict[str, Any]:
    if target_type == FeedbackTarget.FACT:
        value = row.get("fact_value")
        if isinstance(value, dict) and set(value) == {"value"}:
            value = value["value"]
        return {"field": row.get("fact_name"), "value": value}
    if target_type == FeedbackTarget.EVIDENCE:
        return {
            "document_id": str(row.get("document_id")),
            "page": row.get("source_page"),
            "text": row.get("source_text"),
        }
    if target_type == FeedbackTarget.DOCUMENT:
        return {
            "file_name": row.get("file_name"),
            "document_type": row.get("document_type"),
            "processing_status": row.get("processing_status"),
        }
    return {"status": row.get("status"), "task_type": row.get("task_type")}
