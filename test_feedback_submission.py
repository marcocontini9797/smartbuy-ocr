"""
Test Feedback Submission Adapter

Verifica il flusso:

Action Sidebar
        |
        ↓
FeedbackEvent
        |
        ↓
FeedbackSubmission
        |
        ↓
FeedbackService
        |
        ↓
FeedbackReceipt
"""


from document_engine.feedback_submission import (

    submit_feedback

)


from document_engine.action_feedback_bridge import (

    confirm_action_evidence

)


from core.action_models import ActionItem





# ==================================================
# MOCK REPOSITORY
# ==================================================


class MockFeedbackRepository:


    def load_target(self, event):

        """
        Simula il caricamento
        dell'oggetto canonico dal database.

        Deve restituire lo stesso snapshot
        presente nel FeedbackEvent.
        """


        return {

            "id":

                event.target_id,


            "version":

                "v1",


            "payload":

                event.original_payload

        }



    def ingest_atomic(

        self,

        event,

        signal,

        recalculation_stages

    ):

        print("\nRICADUTE CALCOLATE:")

        for stage in recalculation_stages:

            print(

                "-",

                stage

            )


        return {

            "status":

                "accepted"

        }





# ==================================================
# CREAZIONE ACTION SIDEBAR
# ==================================================


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

        "EV001"

    ],


    document_ids=[

        "visura_demo.pdf"

    ]

)





# ==================================================
# CREAZIONE FEEDBACK EVENT
# ==================================================


event = confirm_action_evidence(

    action,


    {

        "tenant_id":

            "demo",


        "property_id":

            16,


        "actor_user_id":

            "agent_001"

    }

)





print("================ EVENTO FEEDBACK ================")


print(

    event.model_dump_json(

        indent=2

    )

)





# ==================================================
# SUBMIT FEEDBACK
# ==================================================


receipt = submit_feedback(

    event,


    MockFeedbackRepository()

)





print("================ RECEIPT ================")


print(

    receipt.model_dump_json(

        indent=2

    )

)