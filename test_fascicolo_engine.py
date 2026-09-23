"""
Test Fascicolo Engine

Simula un fascicolo immobiliare
con più documenti.
"""

from document_engine.fascicolo_engine import build_fascicolo





# ==========================================
# DOCUMENTO 1
# ==========================================

visura = {

    "document_type":

        "visura_catastale",


    "filename":

        "visura_demo.pdf",


    "confidence":

        {

            "extraction":

                0.95

        },


    "extraction":

        {

            "fields":

                {

                    "intestatari":

                        [

                            "Rossi Giovanni"

                        ],


                    "riferimento":

                        {

                            "comune":

                                "Bologna",

                            "foglio":

                                "285",

                            "particella":

                                "789"

                        }

                }

        }

}





# ==========================================
# DOCUMENTO 2
# Simulazione atto
# ==========================================


atto = {


    "document_type":

        "atto_compravendita",


    "filename":

        "atto_demo.pdf",


    "confidence":

        {

            "extraction":

                0.90

        },


    "extraction":

        {

            "fields":

                {

                    "venditore":

                        [

                            "Bianchi Mario"

                        ]

                }

        }

}





# ==========================================
# BUILD FASCICOLO
# ==========================================


result = build_fascicolo(

    [

        visura,

        atto

    ],

    fascicolo_id="IMM-0001"

)



print("\n========== FASCICOLO ==========\n")

print(

    result.model_dump_json(

        indent=2

    )

)