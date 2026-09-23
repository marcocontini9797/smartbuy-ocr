"""
SmartBuy Property Snapshot Models v1

Vista sintetica permanente
del fascicolo immobiliare.
"""


from __future__ import annotations


from typing import Any, Optional


from pydantic import BaseModel, Field





class SnapshotSection(BaseModel):

    """
    Sezione sintetica del report.
    """

    title: str

    items: list[str] = Field(

        default_factory=list

    )





class PropertySnapshot(BaseModel):

    """
    Stato complessivo immobile.
    """

    property_id: int


    status: str = "unknown"


    risk_level: str = "unknown"



    summary: str



    last_update: Optional[str] = None



    documents_section: SnapshotSection



    completed_section: SnapshotSection



    pending_section: SnapshotSection



    issues_section: SnapshotSection



    actions_section: SnapshotSection



    metadata: dict[str, Any] = Field(

        default_factory=dict

    )