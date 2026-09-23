"""
SmartBuy Document Engine - Document Gap Engine

Analizza i rischi individuati e suggerisce
quali documenti aggiuntivi servono per completare
la due diligence.
"""

from __future__ import annotations





DOCUMENT_REQUIREMENTS = {


    "IPO-001":

        [

            "visura_ipotecaria"

        ],



    "URB-001":

        [

            "titoli_edilizi",

            "certificato_conformita_urbanistica"

        ],



    "ENE-001":

        [

            "APE"

        ],



    "CAT-001":

        [

            "planimetria_catastale"

        ]

}





def generate_document_gaps(

    risk_analysis: dict

) -> list[dict]:

    """
    Genera documenti mancanti
    sulla base dei rischi.
    """



    gaps = []


    all_risks = (

        risk_analysis.get("critical", [])

        +

        risk_analysis.get("warnings", [])

        +

        risk_analysis.get("information", [])

    )



    generated = set()



    for risk in all_risks:


        risk_id = risk.get(

            "id"

        )



        required = DOCUMENT_REQUIREMENTS.get(

            risk_id,

            []

        )



        for document in required:


            if document not in generated:


                gaps.append(

                    {

                        "document":

                            document,


                        "source_risk":

                            risk_id,


                        "reason":

                            risk.get(

                                "title",

                                ""

                            )

                    }

                )


                generated.add(

                    document

                )



    return gaps