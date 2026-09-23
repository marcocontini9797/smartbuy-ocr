from document_engine.evidence_engine import (
    build_evidence
)



provenance = [

    {

        "source_document":
            "visura_demo.pdf",

        "source_page":
            1,

        "source_text":
            "Intestatario: Rossi Giovanni",

        "confidence_score":
            0.98

    },


    {

        "source_document":
            "atto_demo.pdf",

        "source_page":
            3,

        "source_text":
            "Venditore: Bianchi Mario",

        "confidence_score":
            0.97

    }

]



result = build_evidence(

    provenance

)



print(result)