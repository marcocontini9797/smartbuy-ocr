from document_engine.agent_service import (

    SmartBuyAgentService

)





class MockRetrieval:



    def retrieve(

        self,

        property_id,

        question

    ):


        return {


            "risk_level":

            "high",


            "sources":

            [

                {

                "document":

                "visura_demo.pdf",

                "page":

                1

                }

            ]

        }





class MockGateway:



    class Response:



        answer = (

            "È presente "

            "una criticità "

            "sulla proprietà."

        )


        confidence = 0.92


        metadata = {

            "grounded":

            True

        }





    def complete(

        self,

        **kwargs

    ):


        return self.Response()





service = SmartBuyAgentService(

    retrieval=MockRetrieval(),

    llm_gateway=MockGateway()

)





result = service.ask(

    property_id=16,

    question=

    "Ci sono problemi sulla proprietà?"

)





print(

    result.model_dump_json(

        indent=2

    )

)