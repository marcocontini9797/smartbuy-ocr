"""
SmartBuy Document Engine - Fascicolo Models

Modelli dati per analisi multi-documento.
"""

from __future__ import annotations


from pydantic import BaseModel, Field

from typing import Optional, Any

from core.models import Issue





# ==================================================
# DOCUMENT MODEL
# ==================================================


class FascicoloDocumento(BaseModel):

    document_id: str

    document_type: str

    filename: Optional[str] = None

    extraction_confidence: float = 0.0

    fields: dict[str, Any] = Field(

        default_factory=dict

    )





# ==================================================
# MISSING DOCUMENT MODEL
# ==================================================


class MissingDocument(BaseModel):

    document_type: str

    reason: str

    priority: str

    required_for: str





# ==================================================
# CROSS CHECK MODEL
# ==================================================


class CrossCheckResult(BaseModel):

    id: str

    category: str

    severity: str

    status: str

    title: str

    message: str

    documents_involved: list[str] = Field(

        default_factory=list

    )





# ==================================================
# RISK MODEL
# ==================================================


class RiskAssessment(BaseModel):

    document_risk: str

    consistency_risk: str

    overall_risk: str





# ==================================================
# FASCICOLO IMMOBILIARE
# ==================================================


class FascicoloImmobiliare(BaseModel):

    fascicolo_id: Optional[str] = None


    documents: list[FascicoloDocumento] = Field(

        default_factory=list

    )


    missing_documents: list[MissingDocument] = Field(

        default_factory=list

    )


    cross_checks: list[CrossCheckResult] = Field(

        default_factory=list

    )


    document_status: dict = Field(

        default_factory=dict

    )


    risk_assessment: RiskAssessment


    completeness_score: float = 0.0


    confidence_score: float = 0.0


    risk_level: str


    # ==================================================
    # SMARTBUY EVALUATION
    # ==================================================

    evaluation: list[Issue] = Field(default_factory=list)
