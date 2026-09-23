"""
SmartBuy Action Models v3.1

Modelli dati sidebar agente.
"""


from __future__ import annotations


from typing import Optional, Any


from uuid import uuid4


from pydantic import BaseModel, Field





class ActionFeedbackOption(BaseModel):

    """
    Azione disponibile nella UI.
    """


    label: str


    feedback_action: str


    description: Optional[str] = None





class ActionItem(BaseModel):

    """
    Singola azione operativa.
    """


    id: str = Field(

        default_factory=lambda:

            str(uuid4())

    )


    status: str


    priority: str = "medium"


    title: str


    reason: str


    action_description: str


    source_type: str


    source_reference: Optional[str] = None



    issue_id: Optional[str] = None


    task_id: Optional[str] = None



    document_ids: list[str] = Field(

        default_factory=list

    )


    evidence_ids: list[str] = Field(

        default_factory=list

    )


    evidence: list[dict[str, Any]] = Field(

        default_factory=list

    )



    resolution_target: Optional[str] = None


    completed: bool = False



    available_actions: list[ActionFeedbackOption] = Field(

        default_factory=list

    )



    metadata: dict[str, Any] = Field(

        default_factory=dict

    )





class ActionSidebar(BaseModel):

    """
    Sidebar persistente agente.
    """


    red: list[ActionItem] = Field(

        default_factory=list

    )


    yellow: list[ActionItem] = Field(

        default_factory=list

    )


    green: list[ActionItem] = Field(

        default_factory=list

    )