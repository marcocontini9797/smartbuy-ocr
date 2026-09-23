"""
SmartBuy Document Engine - Shared Models

Modelli comuni utilizzati da:

- ingestion
- OCR
- classifier
- extraction router
- frontend API
"""

from __future__ import annotations


from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field



# ==================================================
# DOCUMENT TYPES
# ==================================================


class DocumentCategory(str, Enum):

    CATASTO = "catasto"

    URBANISTICA = "urbanistica"

    ENERGETICO = "energetico"

    LEGALE = "legale"

    ALTRO = "altro"



class DocumentType(str, Enum):

    VISURA_CATASTALE = "visura_catastale"

    PLANIMETRIA_CATASTALE = "planimetria_catastale"

    ESTRATTO_MAPPA = "estratto_mappa"

    ATTO_COMPRAVENDITA = "atto_compravendita"

    APE = "ape"

    CILA = "cila"

    SCIA = "scia"

    PERMESSO_COSTRUIRE = "permesso_costruire"

    ALTRO = "altro"



# ==================================================
# FILE METADATA
# ==================================================


class FileMetadata(BaseModel):

    filename: str

    extension: str

    size_bytes: int

    pages: Optional[int] = None

    mime_type: Optional[str] = None

    pdf_creator: Optional[str] = None

    pdf_title: Optional[str] = None

    is_scanned: Optional[bool] = None



# ==================================================
# OCR MODELS
# ==================================================


class OCRPage(BaseModel):

    page_number: int

    text: str

    confidence: float = 0.0



class OCRResult(BaseModel):

    full_text: str

    pages: list[OCRPage]

    confidence: float

    processing_time_seconds: float



# ==================================================
# CLASSIFICATION MODELS
# ==================================================


class ClassificationEvidence(BaseModel):

    source: str

    text: str

    weight: float



class DocumentClassification(BaseModel):

    document_type: DocumentType

    category: DocumentCategory

    confidence: float = Field(

        ge=0,

        le=1

    )

    reason: str

    evidence: list[ClassificationEvidence] = []



# ==================================================
# QUALITY
# ==================================================


class QualityReport(BaseModel):

    ocr_confidence: float

    classification_confidence: float

    extraction_confidence: float

    overall_confidence: float

    warnings: list[str] = []



# ==================================================
# FINAL RESULT
# ==================================================


class DocumentAnalysisResult(BaseModel):

    metadata: FileMetadata

    classification: DocumentClassification

    extracted_fields: Optional[dict[str, Any]] = None

    verification: Optional[dict[str, Any]] = None

    quality: QualityReport

    status: str = "success"