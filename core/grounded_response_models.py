"""
SmartBuy Grounded Response Models v1

Risposte AI con fonti verificabili.
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class ResponseCitation(BaseModel):

    document: str

    page: int | None = None

    text: str





class GroundedResponse(BaseModel):

    answer: str

    explanation: list[str] = Field(

        default_factory=list

    )


    citations: list[ResponseCitation] = Field(

        default_factory=list

    )


    confidence: float = 0


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )