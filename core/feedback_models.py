"""Canonical feedback contracts for SmartBuy document intelligence."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackTarget(str, Enum):
    FACT = "FACT"
    EVIDENCE = "EVIDENCE"
    DOCUMENT = "DOCUMENT"
    ISSUE = "ISSUE"
    MISSING_INFO = "MISSING_INFO"
    RAG_ANSWER = "RAG_ANSWER"
    RAG_RETRIEVAL_ITEM = "RAG_RETRIEVAL_ITEM"
    RECOMMENDATION = "RECOMMENDATION"


class FeedbackAction(str, Enum):
    CONFIRM = "CONFIRM"
    CORRECT = "CORRECT"
    NOT_RELEVANT = "NOT_RELEVANT"
    RESOLVED = "RESOLVED"
    REOPEN = "REOPEN"
    LINK_DOCUMENT = "LINK_DOCUMENT"
    STILL_MISSING = "STILL_MISSING"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    SNOOZE = "SNOOZE"
    START = "START"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"


class FeedbackEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["2.0"] = "2.0"
    feedback_event_id: str = Field(default_factory=lambda: str(uuid4()))
    idempotency_key: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    property_id: int
    actor_user_id: str = Field(min_length=1)
    target_type: FeedbackTarget
    target_id: str = Field(min_length=1)
    expected_version: str = Field(min_length=1)
    action: FeedbackAction
    origin: Literal["USER_EXPLICIT", "EXPERT_REVIEW", "AUTOMATED_EVAL", "SYSTEM_DERIVED"]
    original_payload: dict[str, Any]
    corrected_payload: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str | None = None
    document_id: str | None = None
    analysis_result_id: str | None = None
    rag_run_id: str | None = None
    failure_stage: Literal[
        "UNKNOWN", "OCR", "CLASSIFICATION", "EXTRACTION", "IDENTITY",
        "RETRIEVAL", "RERANKING", "INTERPRETATION", "CROSS_VALIDATION",
        "RULE", "FRESHNESS",
    ] = "UNKNOWN"
    component_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == FeedbackAction.CORRECT and not self.corrected_payload:
            raise ValueError("CORRECT requires corrected_payload")
        if self.action != FeedbackAction.CORRECT and self.corrected_payload is not None:
            raise ValueError("corrected_payload is allowed only for CORRECT")
        if self.action == FeedbackAction.NOT_RELEVANT and not (self.reason or "").strip():
            raise ValueError("NOT_RELEVANT requires a reason")
        if self.action == FeedbackAction.RESOLVED and not self.evidence_ids:
            raise ValueError("RESOLVED requires supporting evidence")
        return self

    def command_hash(self) -> str:
        value = self.model_dump(mode="json", exclude={"feedback_event_id"})
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode()).hexdigest()


class FeedbackSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    signal_id: str
    feedback_event_id: str
    property_id: int
    target_type: str
    target_id: str
    kind: Literal[
        "explicit_correction", "explicit_confirmation", "explicit_rejection",
        "downstream_success", "downstream_failure", "user_override", "abandonment",
    ]
    actor_id: str
    actor_role: Literal["END_USER", "DOMAIN_EXPERT", "SYSTEM", "AUDITOR"]
    payload: dict[str, Any]
    expected_payload: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    document_id: str | None = None
    analysis_result_id: str | None = None
    rag_run_id: str | None = None
    component_versions: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    explicit: bool = True
    occurred_at: str = Field(default_factory=utcnow)


class AgentFeedback(BaseModel):
    """Compatibility model for old callers; new code uses FeedbackEvent."""
    id: Optional[str] = None
    source_type: str
    source_id: Optional[str] = None
    feedback_type: str
    is_correct: Optional[bool] = None
    agent_comment: Optional[str] = None
    corrected_value: Optional[Any] = None
    created_by: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackReceipt(BaseModel):
    feedback_event_id: str
    status: Literal["accepted", "already_processed"]
    signal_id: str
    recalculation_stages: list[str]
