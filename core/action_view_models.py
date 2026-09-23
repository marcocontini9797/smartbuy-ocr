"""
SmartBuy Action View Models v1

Modelli aggregati per la UI agente.

Uniscono:

- action
- evidence
- feedback
- audit

in un unico oggetto leggibile.
"""


from __future__ import annotations


from typing import Any, Optional


from pydantic import BaseModel, Field





class ActionHistoryItem(BaseModel):

    """
    Evento storico mostrato all'agente.
    """


    event_type: str


    description: str


    actor: Optional[str] = None


    timestamp: Optional[str] = None





class SmartBuyActionView(BaseModel):

    """
    Vista completa di un'azione
    per la sidebar agente.
    """


    id: str


    status: str


    priority: str


    title: str


    reason: str


    action_description: str



    source_type: str


    source_reference: Optional[str] = None



    impact: Optional[str] = None



    evidence: list[dict[str, Any]] = Field(

        default_factory=list

    )


    available_actions: list[dict[str, Any]] = Field(

        default_factory=list

    )


    history: list[ActionHistoryItem] = Field(

        default_factory=list

    )



    completed: bool = False



    metadata: dict[str, Any] = Field(

        default_factory=dict

    )