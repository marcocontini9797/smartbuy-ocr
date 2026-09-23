from document_engine.evaluation_engine import (

    EvaluationEngine

)





engine = EvaluationEngine()





response = {


    "answer":

    "Problema intestatario",


    "grounded":

    True,


    "confidence":

    0.9

}





sources=[

    {

    "document":

    "visura_demo.pdf",

    "page":

    1

    }

]





result = engine.evaluate(

    property_id=16,

    response_id="RESP001",

    response=response,

    sources=sources

)





print(

    result.model_dump_json(

        indent=2

    )

)