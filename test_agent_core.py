from document_engine.agent_core import (
    SmartBuyAgentCore
)



from document_engine.unified_retrieval_engine import (
    UnifiedRetrievalEngine
)



from document_engine.llm_context_builder import (
    LLMContextBuilder
)





class MockKnowledge:


    def retrieve_property_context(

        self,

        property_id,

        question

    ):


        return {

            "property_id":property_id,


            "facts":[

                {

                "field":"owner",

                "value":"Rossi Giovanni"

                }

            ],


            "issues":[

                {

                "title":

                "Disallineamento intestatario",

                "severity":

                "high"

                }

            ],


            "evidence":[

                {

                "id":"EV001",

                "document":

                "visura_demo.pdf",

                "page":1,

                "text":

                "Intestatario: Rossi Giovanni",

                "confidence":0.98

                }

            ]

        }





class MockMemory:


    def retrieve(

        self,

        property_id

    ):


        return [

            {

            "title":

            "Proprietario confermato",

            "content":

            {

            "owner":

            "Bianchi Mario"

            }

            }

        ]





class MockLLM:


    def generate(

        self,

        context

    ):


        return {

            "answer":

            "L'immobile presenta una criticità sulla proprietà. È presente una memoria relativa ad una successiva conferma.",


            "explanation":[

                "Disallineamento intestatario",

                "Decisione utente presente in memoria"

            ],


            "sources":[

                {

                "document":

                "visura_demo.pdf",

                "page":1

                }

            ],


            "confidence":0.92

        }





retrieval = UnifiedRetrievalEngine(

    MockKnowledge(),

    MockMemory()

)



agent = SmartBuyAgentCore(

    retrieval,

    LLMContextBuilder(),

    MockLLM()

)





response = agent.ask(

    16,

    "Raccontami la situazione dell'immobile"

)





print(

    response.model_dump_json(

        indent=2

    )

)