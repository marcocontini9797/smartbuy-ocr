"""
SmartBuy Feedback Loop Models v1
"""

from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field


from datetime import datetime, timezone


from uuid import uuid4





def utcnow():

    return datetime.now(

        timezone.utc

    ).isoformat()





class FeedbackDecision(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    property_id: int


    target_type: str


    target_id: str


    action: str


    user_id: str


    corrected_value: Any | None = None


    reason: str | None = None


    created_at: str = Field(

        default_factory=utcnow

    )