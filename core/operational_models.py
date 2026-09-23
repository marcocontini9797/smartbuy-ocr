"""Canonical contracts for the operational document-intelligence pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, Field


SMARTBUY_NAMESPACE = UUID("b89df45e-622e-4e30-bfd7-74db11df8dd7")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(kind: str, *parts: object) -> str:
    value = ":".join([kind, *(str(part).strip() for part in parts)])
    return str(uuid5(SMARTBUY_NAMESPACE, value))


class SourceMode(str, Enum):
    OFFICIAL_LIVE = "official_live"
    OFFICIAL_MANUAL = "official_manual"
    SELLER_DOCUMENT = "seller_document"
    ACCOUNT_UPLOAD = "account_upload"
    EXTERNAL_PUBLIC = "external_public"
    FIXTURE = "fixture"
    SIMULATION = "simulation"


class IntakeRecord(BaseModel):
    intake_id: str
    property_id: int
    document_id: str | None = None
    filename: str
    media_type: str | None = None
    size_bytes: int
    checksum_sha256: str
    source_mode: SourceMode = SourceMode.ACCOUNT_UPLOAD
    received_at: str = Field(default_factory=now_iso)

    @classmethod
    def from_bytes(cls, *, property_id: int, filename: str, content: bytes, media_type: str | None = None):
        checksum = sha256(content).hexdigest()
        return cls(
            intake_id=stable_id("intake", property_id, checksum), property_id=property_id,
            filename=filename, media_type=media_type, size_bytes=len(content), checksum_sha256=checksum,
        )


class PipelineRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    property_id: int
    document_id: str | None = None
    trigger: str = "document_upload"
    status: Literal["queued", "running", "completed", "failed"] = "running"
    component_versions: dict[str, str] = Field(default_factory=dict)
    started_at: str = Field(default_factory=now_iso)
    completed_at: str | None = None
    error: str | None = None


class PipelineStage(BaseModel):
    stage_id: str
    run_id: str
    name: str
    status: Literal["queued", "running", "completed", "failed", "skipped"]
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def completed(cls, run_id: str, name: str, **kwargs: Any):
        return cls(stage_id=stable_id("stage", run_id, name), run_id=run_id, name=name,
                   status="completed", started_at=now_iso(), completed_at=now_iso(), **kwargs)


class OperationalEvidence(BaseModel):
    evidence_id: str
    property_id: int
    run_id: str
    document_id: str | None = None
    kind: str
    source_mode: SourceMode
    source_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    page: int | None = None
    excerpt: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    captured_at: str = Field(default_factory=now_iso)


class DocumentRequest(BaseModel):
    request_id: str
    property_id: int
    document_type: str
    requested_from: str
    reason: str
    legal_basis: str | None = None
    status: Literal["open", "sent", "received", "cancelled"] = "open"
    created_at: str = Field(default_factory=now_iso)

    @classmethod
    def create(cls, *, property_id: int, document_type: str, requested_from: str,
               reason: str, legal_basis: str | None = None):
        return cls(request_id=stable_id("document-request", property_id, document_type, requested_from),
                   property_id=property_id, document_type=document_type,
                   requested_from=requested_from, reason=reason, legal_basis=legal_basis)


class CrossValidationFinding(BaseModel):
    finding_id: str
    property_id: int
    field: str
    status: Literal["consistent", "compatible", "conflict", "extraction_unstable",
                    "insufficient_evidence", "invalid", "attention"]
    values: list[dict[str, Any]]
    evidence_ids: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    label: str | None = None
    severity: Literal["high", "medium", "low"] = "low"
    confidence: float = 0.0
    canonical_value: str | None = None
    sources: list[str] = Field(default_factory=list)
    detail: str | None = None

