"""
SmartBuy Document Models v1

Modelli relativi alla validazione
dell'identità documentale.
"""


from __future__ import annotations


from typing import Optional, Any


from pydantic import BaseModel, Field





class DocumentIdentity(BaseModel):

    """
    Verifica che il documento analizzato
    corrisponda realmente al tipo atteso.
    """


    filename: str


    declared_type: Optional[str] = None


    detected_type: Optional[str] = None


    classification_confidence: float = 0.0


    identity_verified: bool = False


    mismatch_reason: Optional[str] = None


    evidence: list[str] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )