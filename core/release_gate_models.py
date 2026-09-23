"""
SmartBuy Release Gate Models v1
"""

from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field


from uuid import uuid4


from datetime import datetime, timezone





def utcnow():

    return datetime.now(

        timezone.utc

    ).isoformat()





class ReleaseDecision(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    candidate_version: str


    previous_version: str


    candidate_score: float


    previous_score: float


    minimum_score: float


    approved: bool


    decision: str


    reasons: list[str] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )


    created_at: str = Field(

        default_factory=utcnow

    )