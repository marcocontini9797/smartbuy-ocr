"""Compatibility facade for the original AgentFeedback API."""
from __future__ import annotations

from typing import Any

from core.feedback_models import AgentFeedback


def create_feedback(
    source_type: str,
    feedback_type: str,
    source_id: str | None = None,
    is_correct: bool | None = None,
    agent_comment: str | None = None,
    corrected_value: Any = None,
    created_by: str | None = None,
    impact: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentFeedback:
    details = dict(metadata or {})
    if impact is not None:
        details["impact"] = impact
    return AgentFeedback(
        source_type=source_type,
        source_id=source_id,
        feedback_type=feedback_type,
        is_correct=is_correct,
        agent_comment=agent_comment,
        corrected_value=corrected_value,
        created_by=created_by,
        metadata=details,
    )
