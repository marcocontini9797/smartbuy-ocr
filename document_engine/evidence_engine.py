"""
SmartBuy Evidence Engine

Collega anomalie e valutazioni
alle fonti documentali.

Obiettivo:

Problema
    ↓
Evidenza
    ↓
Documento + pagina + testo
"""


def build_evidence(

    document_provenance: list[dict]

) -> list[dict]:


    evidence = []


    for item in document_provenance:


        evidence.append(

            {

                "document":

                    item.get(

                        "source_document"

                    ),


                "page":

                    item.get(

                        "source_page"

                    ),


                "text":

                    item.get(

                        "source_text"

                    ),


                "confidence":

                    item.get(

                        "confidence_score"

                    )

            }

        )


    return evidence





def attach_evidence_to_issue(

    issue: dict,

    provenance: list[dict]

) -> dict:


    issue["evidence"] = build_evidence(

        provenance

    )


    return issue