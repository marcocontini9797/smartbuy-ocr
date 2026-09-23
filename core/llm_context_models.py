"""
SmartBuy LLM Context Models v1

Contratto dati tra SmartBuy
e qualsiasi modello linguistico.
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class LLMSource(BaseModel):

    """
    Fonte utilizzata per generare
    la risposta.
    """

    evidence_id: str | None = None

    document_id: str | None = None

    document: str

    page: int | None = None

    reference_text: str

    confidence: float | None = None





class LLMContextPack(BaseModel):

    """
    Pacchetto finale inviato al modello LLM.
    """

    property_id: int


    user_query: str | None = None



    summary: str



    facts: list[str] = Field(

        default_factory=list

    )



    fact_records: list[dict[str, Any]] = Field(

        default_factory=list

    )



    issues: list[str] = Field(

        default_factory=list

    )



    issue_records: list[dict[str, Any]] = Field(

        default_factory=list

    )



    missing_information: list[dict[str, Any]] = Field(

        default_factory=list

    )



    sources: list[LLMSource] = Field(

        default_factory=list

    )



    instructions: str = (

        "Rispondi utilizzando solamente "

        "le informazioni presenti nel contesto. "

        "Non inventare dati mancanti."

    )



    metadata: dict[str, Any] = Field(

        default_factory=dict

    )
