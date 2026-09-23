"""
SmartBuy Audit Models v1

Modelli per lo storico
delle azioni agente.
"""


from __future__ import annotations


from datetime import datetime, timezone


from typing import Optional, Any


from uuid import uuid4


from pydantic import BaseModel, Field





class ActionAuditEvent(BaseModel):

    """
    Evento storico di una modifica
    effettuata su una action.
    """


    id: str = Field(

        default_factory=lambda:

            str(uuid4())

    )


    action_id: str


    action_type: str


    source_type: str


    source_reference: Optional[str] = None



    actor_id: Optional[str] = None



    previous_status: Optional[str] = None


    new_status: Optional[str] = None



    previous_priority: Optional[str] = None


    new_priority: Optional[str] = None



    timestamp: str = Field(

        default_factory=lambda:

            datetime.now(

                timezone.utc

            ).isoformat()

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )