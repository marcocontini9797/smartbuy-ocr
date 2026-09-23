"""
SmartBuy Impact Propagation Models v1
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class ImpactTarget(BaseModel):

    entity_type: str

    entity_id: str

    reason: str





class ImpactPropagationResult(BaseModel):

    change_type: str

    source_entity: str

    impacted_entities: list[ImpactTarget] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )