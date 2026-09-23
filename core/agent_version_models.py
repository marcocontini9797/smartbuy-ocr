"""
SmartBuy Agent Version Models v1
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





class AgentVersion(BaseModel):


    id: str = Field(

        default_factory=lambda:

        str(uuid4())

    )


    version: str


    status: str


    prompt_version: str


    knowledge_version: str


    model_version: str


    changes: list[str] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )


    created_at: str = Field(

        default_factory=utcnow

    )