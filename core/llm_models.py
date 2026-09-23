"""
SmartBuy LLM Models v1

Contratti astratti
per il livello linguistico.
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class LLMRequest(BaseModel):

    property_id: int

    question: str

    context: dict[str, Any]





class LLMResponse(BaseModel):

    answer: str

    sources: list[str] = Field(

        default_factory=list

    )

    metadata: dict[str, Any] = Field(

        default_factory=dict

    )