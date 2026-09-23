from document_engine.llm_context_builder import (

    LLMContextBuilder

)



import json





retrieved_context = {


    "property_id":16,


    "query":

        "Ci sono problemi sulla proprietà?",



    "facts":[

        {

            "field":

                "owner",

            "value":

                "Rossi Giovanni"

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

            "document":

                "visura_demo.pdf",

            "page":

                1,

            "text":

                "Intestatario: Rossi Giovanni"

        },

        {

            "document":

                "atto_demo.pdf",

            "page":

                3,

            "text":

                "Venditore: Bianchi Mario"

        }

    ],



    "retrieval":{

        "mode":

            "selective",

        "domains":[

            "ownership"

        ]

    }

}





builder = LLMContextBuilder()





context = builder.build(

    retrieved_context

)





print(

    json.dumps(

        context.model_dump(),

        indent=2,

        ensure_ascii=False

    )

)