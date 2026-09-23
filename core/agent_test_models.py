"""
SmartBuy Agent Test Models v1
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





class AgentTestCase(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    name: str


    property_id: int


    question: str


    expected_answer: str


    expected_sources: list[str] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )


    created_at: str = Field(

        default_factory=utcnow

    )





class AgentTestResult(BaseModel):


    test_id: str


    passed: bool


    actual_answer: str


    expected_answer: str


    score: float


    errors: list[str] = Field(

        default_factory=list

    )