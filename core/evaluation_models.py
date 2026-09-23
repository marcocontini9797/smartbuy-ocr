"""
SmartBuy Evaluation Models v1
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





class EvaluationResult(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    property_id: int


    response_id: str


    grounded: bool


    grounding_score: float


    evidence_coverage: float


    confidence_score: float


    overall_score: float


    errors: list[str] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )


    created_at: str = Field(

        default_factory=utcnow

    )