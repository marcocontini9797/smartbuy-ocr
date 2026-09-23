from document_engine.llm_gateway import (
    LLMGateway
)


from document_engine.prompt_manager import (
    PromptManager
)


from core.prompt_models import (
    PromptTemplate
)





class MockProvider:


    def generate(
        self,
        request
    ):

        return {

            "answer":
            "Analisi completata.",

            "model":
            "mock-gpt",

            "confidence":
            0.95

        }





manager = PromptManager()


manager.register(

    PromptTemplate(

        name="property_analysis",

        version="1.0",

        system_prompt="Analizza immobili."

    )

)



gateway = LLMGateway(

    manager,

    MockProvider()

)



response = gateway.complete(

    "property_analysis",

    {

        "property_id":16

    }

)



print(

    response.model_dump_json(

        indent=2

    )

)