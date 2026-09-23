from document_engine.action_execution_engine import execute_action



from core.action_models import ActionItem





class MockFeedbackRepository:


    def load_target(self, event):

        return {

            "id":

                event.target_id,


            "version":

                event.expected_version,


            "payload":

                event.original_payload

        }



    def ingest_atomic(

        self,

        event,

        signal,

        recalculation_stages

    ):

        print("\nSTAGES RICALCOLATI:")

        for stage in recalculation_stages:

            print(

                "-",

                stage

            )


        return {

            "status":

                "accepted"

        }





action = ActionItem(

    status="red",

    priority="high",

    title="Disallineamento intestatario",

    reason=(

        "Visura e atto non coincidono"

    ),

    action_description=(

        "Verificare proprietà"

    ),

    source_type="issue",

    source_reference="ownership_conflict",

    evidence_ids=[

        "EV001",

        "EV002"

    ],

    document_ids=[

        "visura_demo.pdf",

        "atto_demo.pdf"

    ]

)





receipt = execute_action(

    action,

    "CONFIRM",

    MockFeedbackRepository(),

    tenant_id="demo",

    property_id=16,

    actor_user_id="agent_001"

)





print("================ RECEIPT ================")


print(

    receipt.model_dump_json(

        indent=2

    )

)