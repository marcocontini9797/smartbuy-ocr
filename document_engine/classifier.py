"""
SmartBuy Document Engine - Document Classifier

Classificazione intelligente documenti immobiliari.

Principi:
- il nome file NON è affidabile
- il contenuto OCR è la fonte primaria
- ogni classificazione deve avere evidenze
- ogni risultato ha una confidence
"""

from __future__ import annotations


from llm_client import structured_call, LIGHT_MODEL


from .models import (
    DocumentClassification,
    DocumentType,
    DocumentCategory,
    ClassificationEvidence,
    FileMetadata
)



# ==================================================
# PROMPT CLASSIFICAZIONE
# ==================================================

def classification_system_prompt() -> str:

    return """

Sei un classificatore esperto
di documentazione immobiliare italiana.

Devi identificare il tipo documento
partendo esclusivamente dal contenuto.

NON fidarti del nome file.

Tipologie possibili:

CATASO:
- visura_catastale
- planimetria_catastale
- estratto_mappa

ENERGETICO:
- ape

LEGALE:
- atto_compravendita

URBANISTICA:
- cila
- scia
- permesso_costruire

ALTRO:
- altro


Regole:

- cerca evidenze concrete;
- non inventare dati;
- indica sempre il motivo;
- assegna confidence realistica;
- riporta le frasi che hanno guidato la decisione.

"""





# ==================================================
# NORMALIZZAZIONE TESTO
# ==================================================

def normalize_text(text: str) -> str:

    return (
        text
        .replace("\x00", "")
        .strip()
    )





# ==================================================
# CLASSIFICAZIONE LLM
# ==================================================

def classify_document(

    ocr_text: str,

    metadata: FileMetadata

) -> DocumentClassification:


    text = normalize_text(
        ocr_text
    )


    return structured_call(

        system=classification_system_prompt(),


        user=f"""

METADATI FILE:

{metadata.model_dump_json(indent=2)}


TESTO OCR:

{text[:15000]}


Classifica questo documento.

""",

        output_model=DocumentClassification,

        model=LIGHT_MODEL,

    )
# ==================================================
# RULE ENGINE
# ==================================================

def detect_document_rules(

    text: str

) -> tuple[
    DocumentType | None,
    float,
    list[ClassificationEvidence]
]:

    """
    Motore deterministico.

    Cerca indicatori forti
    indipendenti dal modello AI.
    """

    text_lower = text.lower()


    evidence = []


    # ----------------------------------------------
    # VISURA CATASTALE
    # ----------------------------------------------

    score = 0.0


    patterns = [

        (
            "visura catastale",
            0.45
        ),

        (
            "foglio",
            0.15
        ),

        (
            "particella",
            0.15
        ),

        (
            "subalterno",
            0.15
        ),

        (
            "rendita catastale",
            0.10
        ),

    ]


    for pattern, weight in patterns:


        if pattern in text_lower:


            score += weight


            evidence.append(

                ClassificationEvidence(

                    source="rule_engine",

                    text=pattern,

                    weight=weight

                )

            )



    if score >= 0.75:


        return (

            DocumentType.VISURA_CATASTALE,

            score,

            evidence

        )



    # ----------------------------------------------
    # APE
    # ----------------------------------------------

    ape_score = 0

    ape_evidence = []


    ape_patterns = [

        (
            "attestato di prestazione energetica",
            0.5
        ),

        (
            "classe energetica",
            0.25
        ),

        (
            "indice prestazione energetica",
            0.25
        )

    ]


    for pattern, weight in ape_patterns:


        if pattern in text_lower:


            ape_score += weight


            ape_evidence.append(

                ClassificationEvidence(

                    source="rule_engine",

                    text=pattern,

                    weight=weight

                )

            )



    if ape_score >= 0.75:


        return (

            DocumentType.APE,

            ape_score,

            ape_evidence

        )



    # ----------------------------------------------
    # NESSUN MATCH FORTE
    # ----------------------------------------------

    return (

        None,

        0.0,

        []

    )
# ==================================================
# CATEGORY MAPPING
# ==================================================

def category_from_document_type(
    document_type: DocumentType
) -> DocumentCategory:

    mapping = {

        DocumentType.VISURA_CATASTALE:
            DocumentCategory.CATASTO,

        DocumentType.PLANIMETRIA_CATASTALE:
            DocumentCategory.CATASTO,

        DocumentType.ESTRATTO_MAPPA:
            DocumentCategory.CATASTO,

        DocumentType.APE:
            DocumentCategory.ENERGETICO,

        DocumentType.ATTO_COMPRAVENDITA:
            DocumentCategory.LEGALE,

        DocumentType.CILA:
            DocumentCategory.URBANISTICA,

        DocumentType.SCIA:
            DocumentCategory.URBANISTICA,

        DocumentType.PERMESSO_COSTRUIRE:
            DocumentCategory.URBANISTICA,

    }


    return mapping.get(
        document_type,
        DocumentCategory.ALTRO
    )





# ==================================================
# FINAL CLASSIFICATION FUSION
# ==================================================

def classify_with_validation(

    ocr_text: str,

    metadata: FileMetadata

) -> DocumentClassification:


    """
    Classificazione finale SmartBuy.

    Combina:

    - classificazione LLM
    - rule engine

    """



    # 1) Risultato AI

    llm_result = classify_document(
        ocr_text,
        metadata
    )



    # 2) Risultato regole

    rule_type, rule_score, rule_evidence = (
        detect_document_rules(
            ocr_text
        )
    )



    # ----------------------------------------------
    # CASO 1
    # Le regole hanno trovato una prova forte
    # ----------------------------------------------

    if rule_type is not None:


        # Se GPT concorda

        if llm_result.document_type == rule_type:


            confidence = min(

                1.0,

                (
                    llm_result.confidence
                    +
                    rule_score
                )
                /
                2

            )


            reason = (

                "Classificazione confermata "
                "da AI e indicatori documentali"

            )


        # Se GPT non concorda

        else:


            confidence = max(

                rule_score,

                0.85

            )


            reason = (

                "Classificazione corretta "
                "da evidenze documentali forti "
                "nonostante disaccordo AI"

            )



        return DocumentClassification(

            document_type=rule_type,


            category=category_from_document_type(
                rule_type
            ),


            confidence=confidence,


            reason=reason,


            evidence=rule_evidence

        )





    # ----------------------------------------------
    # CASO 2
    # Nessuna regola forte
    # Usiamo GPT
    # ----------------------------------------------


    return DocumentClassification(

        document_type=
            llm_result.document_type,


        category=
            llm_result.category,


        confidence=
            llm_result.confidence,


        reason=
            llm_result.reason,


        evidence=
            llm_result.evidence

    )





# ==================================================
# HUMAN READABLE SUMMARY
# ==================================================

def classification_summary(

    result: DocumentClassification

) -> str:


    evidence = ", ".join(

        [
            item.text
            for item in result.evidence
        ]

    )


    return (

        f"Documento: "
        f"{result.document_type.value}\n"

        f"Categoria: "
        f"{result.category.value}\n"

        f"Affidabilità: "
        f"{round(result.confidence * 100)}%\n"

        f"Motivazione: "
        f"{result.reason}\n"

        f"Evidenze: "
        f"{evidence}"

    )