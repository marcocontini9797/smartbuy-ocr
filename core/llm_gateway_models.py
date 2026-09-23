"""
SmartBuy LLM Gateway Models v1
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field



class LLMRequest(BaseModel):

    task: str

    prompt_version: str

    context: dict[str, Any]


    metadata: dict[str, Any] = Field(
        default_factory=dict
    )




class LLMResponse(BaseModel):

    answer: str

    model: str

    prompt_version: str

    confidence: float = 0.0


    usage: dict[str, Any] = Field(
        default_factory=dict
    )


    metadata: dict[str, Any] = Field(
        default_factory=dict
    )