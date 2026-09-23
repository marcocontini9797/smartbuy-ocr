"""
SmartBuy Knowledge Models v2

Memoria strutturata immobile
con collegamento evidenze.
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class KnowledgeEvidence(BaseModel):

    id: str

    document: str

    page: int | None = None

    text: str

    confidence: float = 0





class KnowledgeFact(BaseModel):

    id: str

    property_id: int

    field: str

    value: Any

    source_document: str | None = None

    confidence: float = 0


    evidence_ids: list[str] = Field(

        default_factory=list

    )





class KnowledgeIssue(BaseModel):

    id: str

    property_id: int

    issue_type: str

    severity: str

    title: str

    status: str = "open"


    evidence_ids: list[str] = Field(

        default_factory=list

    )





class PropertyKnowledgeBase(BaseModel):

    property_id: int


    facts: list[KnowledgeFact] = Field(

        default_factory=list

    )


    evidence: list[KnowledgeEvidence] = Field(

        default_factory=list

    )


    issues: list[KnowledgeIssue] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )