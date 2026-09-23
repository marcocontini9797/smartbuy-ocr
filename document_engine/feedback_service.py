"""Application service connecting validated feedback to Supabase."""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Protocol

from core.feedback_models import (
    FeedbackAction, FeedbackEvent, FeedbackReceipt, FeedbackSignal, FeedbackTarget,
)


class FeedbackConflictError(RuntimeError):
    pass


class FeedbackTargetError(RuntimeError):
    pass


class FeedbackRepository(Protocol):
    def load_target(self, event: FeedbackEvent) -> dict[str, Any] | None: ...
    def ingest_atomic(self, event: FeedbackEvent, signal: FeedbackSignal,
                      recalculation_stages: list[str]) -> dict[str, Any]: ...


_ACTION_KIND = {
    FeedbackAction.CONFIRM: "explicit_confirmation",
    FeedbackAction.CORRECT: "explicit_correction",
    FeedbackAction.NOT_RELEVANT: "explicit_rejection",
    FeedbackAction.RESOLVED: "downstream_success",
    FeedbackAction.REOPEN: "downstream_failure",
    FeedbackAction.LINK_DOCUMENT: "user_override",
    FeedbackAction.STILL_MISSING: "explicit_confirmation",
    FeedbackAction.ACCEPT: "explicit_confirmation",
    FeedbackAction.REJECT: "explicit_rejection",
    FeedbackAction.SNOOZE: "abandonment",
    FeedbackAction.START: "downstream_success",
    FeedbackAction.COMPLETE: "downstream_success",
    FeedbackAction.FAIL: "downstream_failure",
}

_RECALCULATION = {
    FeedbackTarget.FACT: ["cross_validation", "issues", "risk", "actions", "evaluation"],
    FeedbackTarget.EVIDENCE: ["facts", "cross_validation", "issues", "risk", "evaluation"],
    FeedbackTarget.DOCUMENT: ["extraction", "facts", "cross_validation", "issues", "evaluation"],
    FeedbackTarget.ISSUE: ["risk", "actions", "evaluation"],
    FeedbackTarget.MISSING_INFO: ["fascicolo", "issues", "actions", "evaluation"],
    FeedbackTarget.RAG_ANSWER: ["evaluation"],
    FeedbackTarget.RAG_RETRIEVAL_ITEM: ["evaluation"],
    FeedbackTarget.RECOMMENDATION: ["actions", "evaluation"],
}


def build_signal(event: FeedbackEvent, actor_role: str = "END_USER",
                 confidence: float = 1.0) -> FeedbackSignal:
    signal_id = sha256(f"feedback:{event.feedback_event_id}".encode()).hexdigest()[:32]
    return FeedbackSignal(
        signal_id=signal_id,
        feedback_event_id=event.feedback_event_id,
        property_id=event.property_id,
        target_type=event.target_type.value,
        target_id=event.target_id,
        kind=_ACTION_KIND[event.action],
        actor_id=event.actor_user_id,
        actor_role=actor_role,
        payload=event.original_payload,
        expected_payload=event.corrected_payload,
        evidence_ids=event.evidence_ids,
        document_id=event.document_id,
        analysis_result_id=event.analysis_result_id,
        rag_run_id=event.rag_run_id,
        component_versions=event.component_versions,
        confidence=confidence,
    )


class FeedbackService:
    def __init__(self, repository: FeedbackRepository) -> None:
        self.repository = repository

    def submit(self, event: FeedbackEvent, *, actor_role: str = "END_USER") -> FeedbackReceipt:
        target = self.repository.load_target(event)
        if target is None:
            raise FeedbackTargetError("Canonical target does not exist for this property")
        current_version = str(target.get("version") or target.get("updated_at") or target.get("id"))
        if current_version != event.expected_version:
            raise FeedbackConflictError("Target changed after it was shown to the user")
        snapshot = target.get("payload", target)
        if event.original_payload != snapshot:
            raise FeedbackConflictError("Original target snapshot is no longer current")

        signal = build_signal(event, actor_role=actor_role)
        stages = _RECALCULATION[event.target_type]
        result = self.repository.ingest_atomic(event, signal, stages)
        return FeedbackReceipt(
            feedback_event_id=event.feedback_event_id,
            status=result["status"], signal_id=signal.signal_id,
            recalculation_stages=stages,
        )
