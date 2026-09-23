from document_engine.action_click_handler import (

    create_feedback_event

)


from core.action_models import ActionItem





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





event = create_feedback_event(

    action,

    "CONFIRM",

    tenant_id="demo",

    property_id=16,

    actor_user_id="agent_001"

)





print(

    event.model_dump_json(

        indent=2

    )

)