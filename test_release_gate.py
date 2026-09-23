from document_engine.release_gate_engine import (

    ReleaseGateEngine

)





engine = ReleaseGateEngine()





print("================ TEST PASS ================")



result = engine.evaluate(

    candidate_version="1.2",

    previous_version="1.1",

    candidate_score=0.96,

    previous_score=0.92

)



print(

    result.model_dump_json(

        indent=2

    )

)





print("================ TEST FAIL ================")



result = engine.evaluate(

    candidate_version="1.3",

    previous_version="1.2",

    candidate_score=0.85,

    previous_score=0.96

)



print(

    result.model_dump_json(

        indent=2

    )

)