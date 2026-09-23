"""
SmartBuy Monitoring Models v1
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





class AgentMetrics(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    property_count: int = 0


    total_requests: int = 0


    total_errors: int = 0


    average_grounding: float = 0.0


    average_confidence: float = 0.0


    average_score: float = 0.0


    total_input_tokens: int = 0


    total_output_tokens: int = 0


    user_corrections: int = 0


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )


    created_at: str = Field(

        default_factory=utcnow

    )