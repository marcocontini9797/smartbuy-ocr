from document_engine.metrics_collector import (

    MetricsCollector

)





collector = MetricsCollector()





audit = [

    {

    "confidence":0.95,

    "input_tokens":1200,

    "output_tokens":200

    },


    {

    "confidence":0.85,

    "input_tokens":1000,

    "output_tokens":150

    }

]





evaluations=[


    {

    "grounded":True,

    "overall_score":0.95,

    "errors":[]

    },


    {

    "grounded":True,

    "overall_score":0.90,

    "errors":[]

    }

]





feedback=[


    {

    "action":"CORRECT"

    }

]





metrics = collector.collect(

    audit,

    evaluations,

    feedback

)





print(

    metrics.model_dump_json(

        indent=2

    )

)