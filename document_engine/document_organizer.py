"""
SmartBuy Document Organizer Engine v1

Organizza i documenti immobiliari classificati.

Responsabilità:

- assegna cartella logica del fascicolo
- genera nome leggibile
- prepara output utilizzabile da frontend/report
- mantiene evidenze e confidence della classificazione
"""

from __future__ import annotations

from pathlib import Path

from .models import DocumentClassification, DocumentType


# ==================================================
# DOCUMENT ORGANIZATION RULES
# ==================================================

DOCUMENT_FOLDER_MAP = {

    DocumentType.VISURA_CATASTALE:
        "01_Catasto",

    DocumentType.PLANIMETRIA_CATASTALE:
        "01_Catasto",

    DocumentType.ESTRATTO_MAPPA:
        "01_Catasto",

    DocumentType.ATTO_COMPRAVENDITA:
        "02_Provenienza",

    DocumentType.APE:
        "03_Energia",

    DocumentType.CILA:
        "05_Urbanistica",

    DocumentType.SCIA:
        "05_Urbanistica",

    DocumentType.PERMESSO_COSTRUIRE:
        "05_Urbanistica",

    DocumentType.ALTRO:
        "99_Altro",
}


# ==================================================
# DISPLAY NAMES
# ==================================================

DOCUMENT_NAME_MAP = {

    DocumentType.VISURA_CATASTALE:
        "Visura_Catastale",

    DocumentType.PLANIMETRIA_CATASTALE:
        "Planimetria_Catastale",

    DocumentType.ESTRATTO_MAPPA:
        "Estratto_Mappa",

    DocumentType.ATTO_COMPRAVENDITA:
        "Atto_Compravendita",

    DocumentType.APE:
        "APE",

    DocumentType.CILA:
        "CILA",

    DocumentType.SCIA:
        "SCIA",

    DocumentType.PERMESSO_COSTRUIRE:
        "Permesso_Costruire",

    DocumentType.ALTRO:
        "Documento",
}


# ==================================================
# ORGANIZER ENGINE
# ==================================================

def organize_document(
    classification: DocumentClassification,
    filename: str,
    document_id: str | None = None
) -> dict:

    """
    Riceve il risultato del classifier e genera
    la struttura organizzativa del documento.
    """

    document_type = classification.document_type


    folder = DOCUMENT_FOLDER_MAP.get(
        document_type,
        "99_Altro"
    )


    base_name = DOCUMENT_NAME_MAP.get(
        document_type,
        "Documento"
    )


    extension = Path(filename).suffix.lower()


    recommended_name = (
        f"{base_name}{extension}"
    )


    return {

        "document_id": document_id,

        "original_filename": filename,

        "document_type":
            document_type.value,

        "category":
            classification.category.value,

        "recommended_folder":
            folder,

        "recommended_name":
            recommended_name,

        "confidence":
            classification.confidence,

        "classification_reason":
            classification.reason,

        "evidence": [
            e.model_dump()
            for e in classification.evidence
        ]
    }