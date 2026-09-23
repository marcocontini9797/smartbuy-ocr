"""
SmartBuy Agent Service Models v1
"""

from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field


from uuid import uuid4





class AgentQuery(BaseModel):


    property_id: int


    question: str


    user_id: str | None = None


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )





class AgentAnswer(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    property_id: int


    answer: str


    confidence: float


    grounded: bool


    sources: list[dict] = Field(

        default_factory=list

    )


    risk_level: str | None = None


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )