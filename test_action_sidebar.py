from document_engine.action_sidebar_engine import (
    build_action_sidebar
)


from core.models import Evidence, Issue





# ==================================================
# ISSUE CON EVIDENCE
# ==================================================


issue = Issue(

    id="ISSUE-001",

    category="ownership",

    type="ownership_conflict",

    severity="high",

    status="open",

    title="Disallineamento intestatario",

    description=(

        "Il soggetto della visura non coincide "

        "con quello dell'atto."

    ),

    impact=(

        "Possibile blocco della vendita."

    ),

    recommended_action=(

        "Verificare proprietà e atto di provenienza."

    ),


    evidence=[

        Evidence(

            document="visura_demo.pdf",

            page=1,

            text="Intestatario: Rossi Giovanni",

            confidence=0.98,

            metadata={

                "id":"EV001"

            }

        ),


        Evidence(

            document="atto_demo.pdf",

            page=3,

            text="Venditore: Bianchi Mario",

            confidence=0.97,

            metadata={

                "id":"EV002"

            }

        )

    ]

)





missing_documents = [

    {

        "document_type":

            "visura_ipotecaria",

        "priority":

            "high",

        "reason":

            "Necessaria per verificare ipoteche."

    }

]





facts = [

    {

        "name":

            "energy_class",

        "value":

            "A2"

    }

]





sidebar = build_action_sidebar(

    issues=[issue],

    missing_documents=missing_documents,

    facts=facts

)





print(

    sidebar.model_dump_json(

        indent=2

    )

)