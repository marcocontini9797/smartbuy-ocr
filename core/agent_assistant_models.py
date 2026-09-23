"""Canonical response contract for the SmartBuy real-estate copilot."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    PROPERTY_OVERVIEW = "property_overview"
    OWNERSHIP_CHECK = "ownership_check"
    CADASTRAL_CHECK = "cadastral_check"
    URBANISTIC_CHECK = "urbanistic_check"
    ENERGY_CHECK = "energy_check"
    ENCUMBRANCE_CHECK = "encumbrance_check"
    DOCUMENT_GAP = "document_gap"
    CLIENT_EXPLANATION = "client_explanation"
    NEXT_ACTION = "next_action"


class AnswerStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    CONFLICTED = "conflicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ClaimCitation(BaseModel):
    evidence_id: str
    document_id: str | None = None
    document_name: str
    page: int | None = None
    excerpt: str | None = None


class SupportedClaim(BaseModel):
    claim_id: str
    statement: str
    status: AnswerStatus
    fact_ids: list[str] = Field(default_factory=list)
    issue_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AgentNextAction(BaseModel):
    action_id: str
    title: str
    reason: str
    priority: str = "medium"
    responsible_role: str = "agente"
    required_document: str | None = None


class AgentAnswer(BaseModel):
    """UI-ready answer. Every material statement must be traceable."""

    answer_id: str
    property_id: int
    question: str
    intent: AgentIntent
    status: AnswerStatus
    short_answer: str
    claims: list[SupportedClaim] = Field(default_factory=list)
    citations: list[ClaimCitation] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    next_actions: list[AgentNextAction] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

