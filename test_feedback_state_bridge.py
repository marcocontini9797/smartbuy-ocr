from document_engine.feedback_state_bridge import (

    apply_feedback_to_action

)



from core.action_models import ActionItem



from core.feedback_models import FeedbackAction





action = ActionItem(

    status="red",

    priority="high",

    title="Disallineamento intestatario",

    reason="Visura e atto non coincidono",

    action_description="Verificare proprietà",

    source_type="issue",

    source_reference="ownership_conflict"

)





print("================ PRIMA ================")


print(

    action.model_dump_json(

        indent=2

    )

)





updated = apply_feedback_to_action(

    action,

    FeedbackAction.RESOLVED,

    "agent_001"

)





print("================ DOPO RESOLVED ================")


print(

    updated.model_dump_json(

        indent=2

    )

)





updated = apply_feedback_to_action(

    updated,

    FeedbackAction.REOPEN,

    "agent_001"

)





print("================ DOPO REOPEN ================")


print(

    updated.model_dump_json(

        indent=2

    )

)