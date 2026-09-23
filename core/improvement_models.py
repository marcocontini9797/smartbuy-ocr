"""
SmartBuy Continuous Improvement Models v1
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





class ImprovementProposal(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    category: str


    problem: str


    evidence_count: int


    suggestion: str


    target_component: str


    priority: str


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )


    created_at: str = Field(

        default_factory=utcnow

    )