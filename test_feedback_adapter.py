from document_engine.feedback_adapter import (

    create_issue_confirmation,

    create_fact_correction

)





context = {


    "tenant_id":

        "demo",


    "property_id":

        16,


    "actor_user_id":

        "agent_001"

}





issue_feedback = create_issue_confirmation(

    issue_id="CROSS-001",

    issue_payload={

        "title":

            "Disallineamento intestatario",

        "type":

            "ownership_conflict"

    },

    context=context

)





print("================")

print(

    issue_feedback.model_dump_json(

        indent=2

    )

)







fact_feedback = create_fact_correction(

    fact_id="FACT-ENERGY-001",

    original_fact={

        "name":

            "energy_class",

        "value":

            "A2"

    },

    corrected_value="A3",

    context=context

)





print("================")

print(

    fact_feedback.model_dump_json(

        indent=2

    )

)