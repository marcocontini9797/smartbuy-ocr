from document_engine.unified_retrieval_engine import (
    UnifiedRetrievalEngine
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

                "title":"Disallineamento intestatario",

                "severity":"high"

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





engine = UnifiedRetrievalEngine(

    MockKnowledge(),

    MockMemory()

)





result = engine.retrieve(

    16,

    "Cosa sai della proprietà?"

)





print(result)