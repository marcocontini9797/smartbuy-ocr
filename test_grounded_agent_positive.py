from document_engine.grounding_validator import (
    GroundingValidator
)





class MockSource:


    def __init__(self):

        self.document = "visura_demo.pdf"

        self.page = 1





class MockContext:


    sources = [

        MockSource()

    ]





llm_response = {

    "answer":

    "La documentazione evidenzia un problema sulla titolarità.",


    "claims":[

        {

        "text":

        "Problema sulla titolarità",

        "source_required":

        True

        }

    ],


    "confidence":

    0.92

}





validator = GroundingValidator()





result = validator.validate(

    llm_response,

    MockContext()

)





print(result)