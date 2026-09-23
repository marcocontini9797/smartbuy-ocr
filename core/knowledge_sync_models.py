"""
SmartBuy Knowledge Sync Models v1

Modelli per aggiornamenti incrementali
della conoscenza dell'immobile.
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class KnowledgeChange(BaseModel):

    """
    Singola variazione rilevata.
    """


    change_type: str


    property_id: int


    entity_type: str


    entity_id: str | None = None


    field: str | None = None


    old_value: Any = None


    new_value: Any = None


    impacted_entities: list[str] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )