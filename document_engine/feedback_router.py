"""Authenticated feedback endpoint for SmartBuy document intelligence."""
from __future__ import annotations
from typing import Any, Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from api.property_routes import get_property
from api.session import user_client
from core.feedback_models import FeedbackAction, FeedbackEvent, FeedbackReceipt, FeedbackTarget
from document_engine.feedback_service import FeedbackConflictError, FeedbackService, FeedbackTargetError

router = APIRouter(prefix="/api/v1", tags=["feedback"])

class UserFeedbackRequest(BaseModel):
    property_id: int
    target_type: Literal["FACT", "EVIDENCE", "DOCUMENT"]
    target_id: str = Field(min_length=1)
    expected_version: str = Field(min_length=1)
    action: Literal["CONFIRM", "CORRECT", "NOT_RELEVANT"]
    original_payload: dict[str, Any]
    corrected_payload: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str | None = None
    failure_stage: Literal["UNKNOWN", "OCR", "CLASSIFICATION", "EXTRACTION", "IDENTITY", "RETRIEVAL", "RERANKING", "INTERPRETATION", "CROSS_VALIDATION", "RULE", "FRESHNESS"] = "UNKNOWN"
    component_versions: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "CORRECT" and not self.corrected_payload:
            raise ValueError("La correzione richiede il nuovo valore")
        if self.action == "NOT_RELEVANT" and not (self.reason or "").strip():
            raise ValueError("Indica perché il dato non è pertinente")
        return self

@router.post("/feedback", response_model=FeedbackReceipt)
def submit_feedback(request: UserFeedbackRequest, client=Depends(user_client)):
    get_property(request.property_id, client)
    event = FeedbackEvent(
        idempotency_key=request.idempotency_key, tenant_id=client.smartbuy_user_id,
        property_id=request.property_id, actor_user_id=client.smartbuy_user_id,
        target_type=FeedbackTarget(request.target_type), target_id=request.target_id,
        expected_version=request.expected_version, action=FeedbackAction(request.action),
        origin="USER_EXPLICIT", original_payload=request.original_payload,
        corrected_payload=request.corrected_payload, evidence_ids=request.evidence_ids,
        reason=request.reason, failure_stage=request.failure_stage,
        component_versions=request.component_versions,
    )
    from integrations.supabase.feedback_repository import SupabaseFeedbackRepository
    try:
        return FeedbackService(SupabaseFeedbackRepository(client)).submit(event, actor_role="END_USER")
    except FeedbackTargetError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FeedbackConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "Feedback persistence is not configured") from exc
