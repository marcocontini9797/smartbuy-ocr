from .facts_repository import save_extracted_fact


def map_extraction_to_facts(
    extraction_result,
    property_id,
    document_id,
    analysis_result_id,
    source_document,
    default_confidence=0.95
):
    """
    Trasforma il risultato dell'extraction engine
    in property_facts + fact_provenance.

    Supporta due formati:

    1) semplice:

    {
        "energy_class": "B",
        "epgl": 74
    }


    2) avanzato:

    {
        "energy_class": {
            "value": "B",
            "confidence": 0.98,
            "source_page": 2,
            "source_text": "Classe energetica B"
        }
    }

    """


    saved_facts = []


    for key, value in extraction_result.items():

        if value is None:
            continue


        confidence = default_confidence
        source_page = None
        source_text = None
        real_value = value


        # formato avanzato
        if isinstance(value, dict):

            real_value = value.get(
                "value",
                value
            )

            confidence = value.get(
                "confidence",
                default_confidence
            )

            source_page = value.get(
                "source_page"
            )

            source_text = value.get(
                "source_text"
            )


        result = save_extracted_fact(

            analysis_result_id=analysis_result_id,

            property_id=property_id,

            document_id=document_id,

            fact_name=key,

            fact_value=real_value,

            source_document=source_document,

            source_page=source_page,

            source_text=source_text,

            confidence=confidence

        )


        saved_facts.append(

            {
                "fact_name": key,
                "value": real_value,
                "confidence": confidence,
                "result": result
            }

        )


    return saved_facts