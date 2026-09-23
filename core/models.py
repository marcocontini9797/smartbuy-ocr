"""
SmartBuy Core Models v2

Modelli dati fondamentali condivisi
da tutti i motori del sistema.

Oggetti principali:

Fact
Evidence
Issue

Pensati per:
- analisi documentale
- due diligence immobiliare
- supporto agente immobiliare
"""


from __future__ import annotations


from typing import Any, Optional


from pydantic import BaseModel, Field





# ==================================================
# FACT MODEL
# ==================================================


class Fact(BaseModel):

    """
    Informazione estratta e validata.

    Esempio:

    energy_class = A2
    """

    id: Optional[str] = None


    name: str


    value: Any


    # Categoria del fatto

    # esempi:
    # energy
    # ownership
    # cadastral
    # urbanistic

    category: Optional[str] = None



    # Origine informazione

    source_type: Optional[str] = None



    # Affidabilità estrazione

    confidence: float = 0.0



    # Stato verifica

    # pending
    # verified
    # corrected

    verification_status: str = "pending"



    # Eventuale valore corretto
    # inserito dopo revisione umana

    verified_value: Optional[Any] = None



    metadata: dict[str, Any] = Field(

        default_factory=dict

    )





# ==================================================
# EVIDENCE MODEL
# ==================================================


class Evidence(BaseModel):

    """
    Fonte documentale che supporta
    un fatto o una decisione.

    Utilizzata per audit e verifica.
    """

    document: str



    page: Optional[int] = None



    text: Optional[str] = None



    confidence: float = 0.0



    metadata: dict[str, Any] = Field(

        default_factory=dict

    )





# ==================================================
# ISSUE MODEL v2
# ==================================================


class Issue(BaseModel):

    """
    Problema, rischio o attività
    individuata dal sistema.

    Strutturato per l'agente immobiliare.
    """

    id: Optional[str] = None



    # Area del problema

    # ownership
    # cadastral
    # urbanistic
    # energy
    # documentation

    category: str = "general"



    # Tipo tecnico

    # esempio:
    # ownership_conflict
    # missing_document

    type: str



    # Gravità

    # low
    # medium
    # high

    severity: str = "medium"



    # Stato gestione

    # open
    # reviewing
    # resolved

    status: str = "open"



    # Titolo leggibile

    title: str



    # Descrizione problema

    description: str



    # Impatto commerciale

    impact: Optional[str] = None



    # Azione consigliata

    recommended_action: Optional[str] = None



    # Evidenze collegate

    evidence: list[Evidence] = Field(

        default_factory=list

    )



    # Dati aggiuntivi

    metadata: dict[str, Any] = Field(

        default_factory=dict

    )