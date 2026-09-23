"""Contracts for sale and rental workflows handled by SmartBuy."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PropertyPurpose(str, Enum):
    SALE = "sale"
    RENT_LONG_TERM = "rent_long_term"
    RENT_TRANSITORY = "rent_transitory"
    RENT_STUDENT = "rent_student"
    RENT_SHORT_TERM = "rent_short_term"


class WorkflowStage(str, Enum):
    INTAKE = "intake"
    LISTING_READY = "listing_ready"
    NEGOTIATION = "negotiation"
    CONTRACT_READY = "contract_ready"
    POST_CONTRACT = "post_contract"


class RequirementLevel(str, Enum):
    MANDATORY = "mandatory"
    HIGHLY_RECOMMENDED = "highly_recommended"


class PlaybookRequirement(BaseModel):
    requirement_id: str
    domain: str
    title: str
    why_it_matters: str
    level: RequirementLevel = RequirementLevel.HIGHLY_RECOMMENDED
    legal_note: str | None = None
    expected_documents: list[str] = Field(default_factory=list)
    blocking: bool = False
    professional_review: str | None = None


class PropertyFlowPlaybook(BaseModel):
    purpose: PropertyPurpose
    stages: list[WorkflowStage]
    requirements: list[PlaybookRequirement]
    agent_questions: list[str] = Field(default_factory=list)
    output_sections: list[str] = Field(default_factory=list)
