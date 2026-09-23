"""
SmartBuy Document Engine - Fascicolo Engine v2.2

Motore di analisi multi-documento.

Funzioni:

- aggregazione documenti
- verifica completezza
- document gap con priorità
- cross check documentali
- risk assessment fascicolo
- evaluation semaforica 🟢🟡🔴
"""

from __future__ import annotations


from typing import List
from uuid import uuid4


from .fascicolo_models import (
    FascicoloDocumento,
    MissingDocument,
    CrossCheckResult,
    FascicoloImmobiliare,
    RiskAssessment
)


from .evaluation_engine import (
    evaluate_fascicolo
)



# ==================================================
# DOCUMENT WEIGHTS
# ==================================================


DOCUMENT_WEIGHTS = {

    "atto_compravendita": 25,

    "visura_catastale": 20,

    "visura_ipotecaria": 20,

    "planimetria_catastale": 15,

    "titoli_edilizi": 10,

    "ape": 10

}



# ==================================================
# DOCUMENT PRIORITY
# ==================================================


DOCUMENT_PRIORITY = {

    "atto_compravendita": {

        "priority": "high",

        "reason":
            "Necessario per verificare trasferimento proprietà e soggetti coinvolti.",

        "required_for":
            "verifica proprietà"

    },


    "visura_ipotecaria": {

        "priority": "high",

        "reason":
            "Necessaria per verificare ipoteche, gravami e vincoli.",

        "required_for":
            "verifica vincoli"

    },


    "planimetria_catastale": {

        "priority": "medium",

        "reason":
            "Necessaria per verificare coerenza geometrica dell'immobile.",

        "required_for":
            "verifica catastale"

    },


    "titoli_edilizi": {

        "priority": "medium",

        "reason":
            "Necessari per verificare conformità urbanistica.",

        "required_for":
            "verifica urbanistica"

    },


    "ape": {

        "priority": "low",

        "reason":
            "Necessario per verificare prestazioni energetiche.",

        "required_for":
            "verifica energetica"

    }

}



# ==================================================
# NORMALIZE DOCUMENT
# ==================================================


def normalize_document(document: dict) -> FascicoloDocumento:


    return FascicoloDocumento(

        document_id=str(uuid4()),

        document_type=document.get(

            "document_type",

            "unknown"

        ),

        filename=document.get(

            "filename"

        ),

        extraction_confidence=document.get(

            "confidence",

            {}

        ).get(

            "extraction",

            0.0

        ),

        fields=document.get(

            "extraction",

            {}

        ).get(

            "fields",

            {}

        )

    )



# ==================================================
# MISSING DOCUMENTS
# ==================================================


def detect_missing_documents(

    documents: List[FascicoloDocumento]

) -> list[MissingDocument]:


    present = {

        doc.document_type

        for doc in documents

    }


    missing = []


    for document_type in DOCUMENT_WEIGHTS:


        if document_type not in present:


            meta = DOCUMENT_PRIORITY[document_type]


            missing.append(

                MissingDocument(

                    document_type=document_type,

                    reason=meta["reason"],

                    priority=meta["priority"],

                    required_for=meta["required_for"]

                )

            )


    return missing



# ==================================================
# DOCUMENT STATUS
# ==================================================


def build_document_status(

    documents,

    missing

):


    return {

        "present":

            [

                d.document_type

                for d in documents

            ],


        "missing":

            [

                d.document_type

                for d in missing

            ]

    }



# ==================================================
# COMPLETENESS SCORE
# ==================================================


def calculate_completeness_score(documents):


    total = sum(

        DOCUMENT_WEIGHTS.values()

    )


    present = sum(

        DOCUMENT_WEIGHTS.get(

            d.document_type,

            0

        )

        for d in documents

    )


    return round(

        present / total * 100,

        1

    )



# ==================================================
# CROSS CHECK
# ==================================================


def run_cross_checks(documents):


    results = []


    visura = None

    atto = None



    for doc in documents:


        if doc.document_type == "visura_catastale":

            visura = doc


        elif doc.document_type == "atto_compravendita":

            atto = doc




    if visura and atto:


        catasto_owner = visura.fields.get(

            "intestatari",

            []

        )


        deed_owner = atto.fields.get(

            "venditore",

            []

        )



        if (

            catasto_owner

            and deed_owner

            and catasto_owner != deed_owner

        ):


            results.append(

                CrossCheckResult(

                    id="CROSS-001",

                    category="proprietà",

                    severity="high",

                    status="anomaly",

                    title="Disallineamento intestatario",

                    message=
                        "Il soggetto indicato nella visura catastale non coincide con quello indicato nell'atto.",

                    documents_involved=[

                        "visura_catastale",

                        "atto_compravendita"

                    ]

                )

            )


    return results



# ==================================================
# RISK ASSESSMENT
# ==================================================


def calculate_risk_assessment(

    missing_documents,

    cross_checks

):


    document_risk = "low"

    consistency_risk = "low"



    if len(missing_documents) >= 3:

        document_risk = "medium"



    if len(missing_documents) >= 5:

        document_risk = "high"




    for check in cross_checks:


        if check.severity == "high":

            consistency_risk = "high"


        elif check.severity == "medium":

            consistency_risk = "medium"




    overall = "low"



    if (

        document_risk == "high"

        or consistency_risk == "high"

    ):

        overall = "high"


    elif (

        document_risk == "medium"

        or consistency_risk == "medium"

    ):

        overall = "medium"




    return RiskAssessment(

        document_risk=document_risk,

        consistency_risk=consistency_risk,

        overall_risk=overall

    )



# ==================================================
# CONFIDENCE
# ==================================================


def calculate_confidence_score(documents):


    if not documents:

        return 0.0



    return round(

        sum(

            d.extraction_confidence

            for d in documents

        )

        /

        len(documents),

        2

    )



# ==================================================
# BUILD FASCICOLO
# ==================================================


def build_fascicolo(

    documents: list[dict],

    fascicolo_id: str | None = None

):


    normalized = [

        normalize_document(d)

        for d in documents

    ]



    missing = detect_missing_documents(

        normalized

    )



    cross_checks = run_cross_checks(

        normalized

    )



    document_status = build_document_status(

        normalized,

        missing

    )



    risk_assessment = calculate_risk_assessment(

        missing,

        cross_checks

    )



    evaluation = evaluate_fascicolo(

        [

            {

                "document_type":

                    d.document_type,

                "extraction_confidence":

                    d.extraction_confidence

            }

            for d in normalized

        ],


        [

            {

                "document_type":

                    m.document_type,

                "priority":

                    m.priority,

                "reason":

                    m.reason

            }

            for m in missing

        ],


        [

            {

                "severity":

                    c.severity,

                "title":

                    c.title,

                "message":

                    c.message

            }

            for c in cross_checks

        ],


        risk_assessment.model_dump()

    )



    return FascicoloImmobiliare(

        fascicolo_id=fascicolo_id,

        documents=normalized,

        missing_documents=missing,

        cross_checks=cross_checks,

        document_status=document_status,

        risk_assessment=risk_assessment,

        completeness_score=

            calculate_completeness_score(

                normalized

            ),

        confidence_score=

            calculate_confidence_score(

                normalized

            ),

        risk_level=

            risk_assessment.overall_risk,

        evaluation=evaluation

    )