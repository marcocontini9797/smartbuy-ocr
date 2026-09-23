from document_engine.sidebar_state_engine import (

    complete_action,

    reopen_action,

    snooze_action

)



from core.action_models import ActionItem





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





complete_action(

    action,

    "agent_001"

)





print("================ COMPLETATA ================")


print(

    action.model_dump_json(

        indent=2

    )

)





reopen_action(

    action,

    "agent_001"

)





print("================ RIAPERTA ================")


print(

    action.model_dump_json(

        indent=2

    )

)