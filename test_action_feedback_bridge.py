from document_engine.action_feedback_bridge import (

    confirm_action_evidence

)


from core.action_models import ActionItem





action = ActionItem(

    status="red",

    priority="high",

    title="Disallineamento intestatario",

    reason="Visura e atto non coincidono",

    action_description="Verificare proprietà",

    source_type="issue",

    source_reference="ownership_conflict",

    evidence_ids=[

        "EV001"

    ],

    document_ids=[

        "visura_demo.pdf"

    ]

)





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





print(

    event.model_dump_json(

        indent=2

    )

)