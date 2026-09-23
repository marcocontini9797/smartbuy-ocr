"""
SmartBuy Event Models v1

Eventi interni del sistema.
"""


from __future__ import annotations


from datetime import datetime, timezone


from typing import Any


from uuid import uuid4


from pydantic import BaseModel, Field





def utcnow():

    return datetime.now(

        timezone.utc

    ).isoformat()





class SmartBuyEvent(BaseModel):


    event_id: str = Field(

        default_factory=lambda:

            str(uuid4())

    )


    event_type: str


    property_id: int


    entity_type: str


    entity_id: str


    payload: dict[str, Any]


    created_at: str = Field(

        default_factory=utcnow

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )