from core.prompt_models import (
    PromptTemplate
)


from document_engine.prompt_manager import (
    PromptManager
)





manager = PromptManager()





prompt = PromptTemplate(

    name="property_analysis",

    version="1.0",


    system_prompt=

    """

    Sei SmartBuy Agent.

    Analizza immobili usando

    solamente informazioni verificate.

    """,


    rules=[

        "Non inventare informazioni",

        "Usa sempre le evidenze",

        "Cita i documenti"

    ]

)





manager.register(

    prompt

)





loaded = manager.get(

    "property_analysis",

    "1.0"

)





print(

    loaded.model_dump_json(

        indent=2

    )

)