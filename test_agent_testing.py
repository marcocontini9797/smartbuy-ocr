from core.agent_test_models import (

    AgentTestCase

)


from document_engine.agent_test_engine import (

    AgentTestEngine

)





class MockAgent:



    def ask(

        self,

        property_id,

        question

    ):


        return {


            "answer":

            "Il proprietario è Bianchi Mario"


        }





agent = MockAgent()



engine = AgentTestEngine(

    agent

)





test = AgentTestCase(

    name=

    "Verifica proprietario",


    property_id=16,


    question=

    "Chi è il proprietario?",


    expected_answer=

    "Bianchi Mario"

)





result = engine.run(

    test

)



print(

    result.model_dump_json(

        indent=2

    )

)