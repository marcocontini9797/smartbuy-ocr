"""
SmartBuy Document Engine - Extraction Router v3

Pipeline:

OCR
 |
Classifier
 |
Router
 |
Extraction
 |
Verification
 |
Confidence Engine
 |
Risk Engine v2
 |
Document Gap Engine
 |
Supabase Sync
"""

from __future__ import annotations

from typing import Optional, Any


from schemas import (
    SCHEMA_REGISTRY,
    TipoDocumento
)


from extraction import (
    extract_document_verified
)


from .models import (
    DocumentClassification
)


from .risk_engine import (
    generate_risk_analysis,
    risk_summary
)


from .document_gap_engine import (
    generate_document_gaps
)


from .pipeline_sync import (
    sync_extraction_pipeline
)


# ==================================================
# TYPE CONVERSION
# ==================================================


def map_document_type(
    document_type: str
) -> Optional[TipoDocumento]:

    try:
        return TipoDocumento(
            document_type
        )

    except Exception:

        return None



# ==================================================
# SCHEMA CHECK
# ==================================================


def has_extraction_schema(
    document_type: TipoDocumento
) -> bool:

    return document_type in SCHEMA_REGISTRY



# ==================================================
# EXTRACTION + VERIFICATION
# ==================================================


def extract_document_with_verification(

    ocr_text: str,

    classification: DocumentClassification

) -> dict[str, Any]:


    tipo = map_document_type(

        classification.document_type.value

    )


    if tipo is None:

        return {

            "status": "unsupported_document",

            "document_type":
                classification.document_type.value,

            "fields": None,

            "verification": None

        }



    if not has_extraction_schema(tipo):

        return {

            "status": "schema_missing",

            "document_type":
                tipo.value,

            "fields": None,

            "verification": None

        }



    try:

        extracted, verification = (

            extract_document_verified(

                ocr_text,

                tipo

            )

        )


        return {

            "status":
                "success",

            "document_type":
                tipo.value,

            "fields":
                extracted.model_dump(

                    exclude_none=True,

                    mode="json"

                ),


            "verification":

                verification.model_dump(

                    exclude_none=True,

                    mode="json"

                )

        }



    except Exception as e:


        return {

            "status":
                "extraction_error",

            "document_type":
                tipo.value,

            "fields":
                None,

            "verification":
                None,

            "error":
                str(e)

        }



# ==================================================
# CONFIDENCE
# ==================================================


def calculate_extraction_confidence(

    extraction_result: dict

) -> float:


    if extraction_result.get("status") != "success":

        return 0.0



    fields = extraction_result.get("fields")


    verification = extraction_result.get("verification")



    if not fields:

        return 0.2



    score = 0.5



    if len(fields) >= 5:

        score += 0.2


    elif len(fields) >= 2:

        score += 0.1



    if verification:


        if verification.get(
            "tutti_i_campi_supportati",
            False
        ):

            score += 0.25


        elif verification.get(
            "campi_non_supportati"
        ):

            score -= 0.20



    return round(

        min(max(score, 0), 1),

        3

    )



def calculate_overall_confidence(

    ocr_confidence: float,

    classification_confidence: float,

    extraction_confidence: float

) -> float:


    score = (

        ocr_confidence * 0.30

        +

        classification_confidence * 0.30

        +

        extraction_confidence * 0.40

    )


    return round(

        score,

        3

    )



# ==================================================
# WARNINGS
# ==================================================


def extract_agent_warnings(

    extraction: dict

) -> list[dict]:


    warnings = []


    verification = extraction.get(
        "verification"
    )


    if not verification:

        return warnings



    text = verification.get(

        "osservazioni_generali",

        ""

    ).lower()



    if "non verificabile" in text:


        warnings.append(

            {

                "type":
                    "verification_required",

                "severity":
                    "medium",

                "message":
                    "Alcune informazioni richiedono verifica tramite documentazione aggiuntiva."

            }

        )


    return warnings



# ==================================================
# BUILD RESULT
# ==================================================


def build_document_result(

    ocr_text: str,

    classification: DocumentClassification,

    property_id: int | None = None,

    document_id: int | None = None,

    analysis_result_id: str | None = None,

    source_document: str | None = None

) -> dict:


    extraction = extract_document_with_verification(

        ocr_text,

        classification

    )



    extraction_confidence = calculate_extraction_confidence(

        extraction

    )



    overall_confidence = calculate_overall_confidence(

        0.95,

        classification.confidence,

        extraction_confidence

    )



    warnings = extract_agent_warnings(

        extraction

    )



    risk_analysis = generate_risk_analysis(

        extraction

    )


    risk_overview = risk_summary(

        risk_analysis

    )



    document_gaps = generate_document_gaps(

        risk_analysis

    )



    if extraction_confidence >= 0.85:

        quality_status = "verified"


    elif extraction_confidence >= 0.60:

        quality_status = "review_required"


    else:

        quality_status = "manual_check_required"



    # ------------------------------
    # SUPABASE SYNC
    # ------------------------------

    supabase_sync = None


    if (

        property_id

        and document_id

        and analysis_result_id

        and source_document

    ):

        supabase_sync = sync_extraction_pipeline(

            document_result={

                "extraction": extraction

            },

            property_id=property_id,

            document_id=document_id,

            analysis_result_id=analysis_result_id,

            source_document=source_document

        )



    return {


        "document_type":

            classification.document_type.value,


        "category":

            classification.category.value,


        "classification": {

            "confidence":

                classification.confidence,

            "reason":

                classification.reason,

            "evidence":

            [

                e.model_dump(

                    mode="json"

                )

                for e in classification.evidence

            ]

        },


        "extraction":

            extraction,


        "confidence": {

            "ocr":

                0.95,

            "classification":

                classification.confidence,

            "extraction":

                extraction_confidence,

            "overall":

                overall_confidence

        },


        "insights": {

            "warnings":

                warnings,

            "risk_analysis":

                risk_analysis,

            "risk_summary":

                risk_overview,

            "document_gaps":

                document_gaps

        },


        "quality": {

            "status":

                quality_status

        },


        "supabase_sync":

            supabase_sync

    }



# ==================================================
# FASCICOLO
# ==================================================


def build_fascicolo_result(

    documents: list[dict]

) -> dict:


    document_types = [

        d.get("document_type")

        for d in documents

    ]


    required_documents = [

        "visura_catastale",

        "ape",

        "atto_compravendita",

        "visura_ipotecaria"

    ]


    missing = [

        doc

        for doc in required_documents

        if doc not in document_types

    ]


    return {


        "total_documents":

            len(documents),


        "documents":

            documents,


        "missing_documents":

            missing,


        "complete":

            len(missing) == 0

    }