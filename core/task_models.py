"""
SmartBuy Task Models v1

Modelli per attività operative
generate dagli issue.

Pensato per workflow agente immobiliare.
"""


from __future__ import annotations


from typing import Optional, Any


from pydantic import BaseModel, Field





class Task(BaseModel):

    """
    Attività operativa generata
    da una criticità.
    """


    id: Optional[str] = None



    # tipo attività

    # verification
    # request_document
    # technical_check
    # review

    task_type: str



    title: str



    description: str



    priority: str = "medium"



    status: str = "open"



    # chi deve occuparsene

    assigned_role: str = "agente immobiliare"



    # se impedisce vendita

    blocking: bool = False



    # issue origine

    source_issue: Optional[str] = None



    metadata: dict[str, Any] = Field(

        default_factory=dict

    )