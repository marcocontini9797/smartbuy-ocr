from document_engine.continuous_improvement_engine import (

    ContinuousImprovementEngine

)





engine = ContinuousImprovementEngine()





evaluations=[


    {

    "errors":

    [

    "unsupported claim"

    ]

    },


    {

    "errors":

    [

    "missing evidence"

    ]

    }

]





feedback=[


    {

    "action":

    "CORRECT"

    },


    {

    "action":

    "CORRECT"

    }

]





result = engine.analyze(

    evaluations,

    feedback

)





for item in result:

    print(

        item.model_dump_json(

            indent=2

        )

    )