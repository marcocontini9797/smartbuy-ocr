from core.llm_audit_models import (
    LLMAuditRecord
)




record = LLMAuditRecord(

    property_id=16,

    user_query=

    "Ci sono problemi sulla proprietà?",


    task=

    "property_analysis",


    prompt_version=

    "1.0",


    model=

    "mock-gpt",


    answer=

    "È presente una criticità sulla titolarità.",


    confidence=

    0.92,


    grounded=

    True,


    input_tokens=

    1500,


    output_tokens=

    300

)





print(

    record.model_dump_json(

        indent=2

    )

)