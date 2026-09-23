"""
SmartBuy LLM Audit Models v1
"""

from __future__ import annotations


from typing import Any


from datetime import datetime, timezone


from uuid import uuid4


from pydantic import BaseModel, Field





def utcnow():

    return datetime.now(

        timezone.utc

    ).isoformat()





class LLMAuditRecord(BaseModel):


    id: str = Field(

        default_factory=lambda:

            str(uuid4())

    )


    property_id: int


    user_query: str


    task: str


    prompt_version: str


    model: str


    answer: str


    confidence: float = 0.0


    grounded: bool = False


    input_tokens: int = 0


    output_tokens: int = 0


    context_hash: str | None = None


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )


    created_at: str = Field(

        default_factory=utcnow

    )