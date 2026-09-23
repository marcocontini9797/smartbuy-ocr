"""
SmartBuy Agent Models v1
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class AgentResponse(BaseModel):


    answer: str


    explanation: list[str] = Field(

        default_factory=list

    )


    sources: list[dict[str, Any]] = Field(

        default_factory=list

    )


    memory_used: bool = False


    confidence: float = 0.0


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )