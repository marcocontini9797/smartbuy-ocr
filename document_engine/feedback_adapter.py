"""Convenience builders used by the agent UI and legacy tests."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from core.feedback_models import FeedbackEvent


def _idempotency(action: str, target_id: str, payload: dict[str, Any], context: dict) -> str:
    supplied = context.get("idempotency_key")
    if supplied:
        return str(supplied)
    raw = json.dumps(
        [context.get("tenant_id"), context.get("property_id"), action, target_id, payload],
        sort_keys=True, default=str,
    )
    return sha256(raw.encode()).hexdigest()


def create_issue_confirmation(issue_id: str, issue_payload: dict[str, Any],
                              context: dict[str, Any]) -> FeedbackEvent:
    return FeedbackEvent(
        idempotency_key=_idempotency("CONFIRM", issue_id, issue_payload, context),
        tenant_id=str(context["tenant_id"]), property_id=int(context["property_id"]),
        actor_user_id=str(context["actor_user_id"]), target_type="ISSUE",
        target_id=str(issue_id), expected_version=str(context.get("expected_version", issue_id)),
        action="CONFIRM", origin=context.get("origin", "USER_EXPLICIT"),
        original_payload=issue_payload,
        evidence_ids=context.get("evidence_ids", []),
        document_id=context.get("document_id"), rag_run_id=context.get("rag_run_id"),
        component_versions=context.get("component_versions", {}),
    )


def create_fact_correction(fact_id: str, original_fact: dict[str, Any],
                           corrected_value: Any, context: dict[str, Any]) -> FeedbackEvent:
    corrected = dict(original_fact)
    corrected["value"] = corrected_value
    return FeedbackEvent(
        idempotency_key=_idempotency("CORRECT", fact_id, corrected, context),
        tenant_id=str(context["tenant_id"]), property_id=int(context["property_id"]),
        actor_user_id=str(context["actor_user_id"]), target_type="FACT",
        target_id=str(fact_id), expected_version=str(context.get("expected_version", fact_id)),
        action="CORRECT", origin=context.get("origin", "USER_EXPLICIT"),
        original_payload=original_fact, corrected_payload=corrected,
        evidence_ids=context.get("evidence_ids", []),
        document_id=context.get("document_id"),
        analysis_result_id=context.get("analysis_result_id"),
        rag_run_id=context.get("rag_run_id"),
        failure_stage=context.get("failure_stage", "UNKNOWN"),
        component_versions=context.get("component_versions", {}),
    )
