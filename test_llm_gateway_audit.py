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

            0.95,


            "grounded":

            True,


            "usage":

            {

                "input_tokens":1200,

                "output_tokens":200

            }

        }





class MockAuditRepository:



    def __init__(self):

        self.logs=[]





    def save(

        self,

        record

    ):

        self.logs.append(

            record

        )





manager = PromptManager()



manager.register(

    PromptTemplate(

        name="property_analysis",

        version="1.0",

        system_prompt=

        "Analizza immobili."

    )

)





audit = MockAuditRepository()





gateway = LLMGateway(

    manager,

    MockProvider(),

    audit

)





response = gateway.complete(

    task="property_analysis",

    context={

        "property_id":16

    },

    property_id=16,

    user_query=

    "Ci sono problemi sulla proprietà?"

)





print("================ RESPONSE ================")

print(

    response.model_dump_json(

        indent=2

    )

)



print("================ AUDIT ================")

print(

    audit.logs

)