from document_engine.evidence_mapper import (
    map_evidence_list,
    debug_print_evidence
)



raw_evidence = [

    {

        "document":

            "visura_demo.pdf",

        "page":

            1,

        "text":

            "Intestatario: Rossi Giovanni",

        "confidence":

            0.98

    },

    {

        "document":

            "atto_demo.pdf",

        "page":

            3,

        "text":

            "Venditore: Bianchi Mario",

        "confidence":

            0.97

    }

]



evidence = map_evidence_list(

    raw_evidence

)



debug_print_evidence(

    evidence

)