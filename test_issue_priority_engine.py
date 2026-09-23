from document_engine.issue_priority_engine import (
    prioritize_issues
)

from document_engine.evaluation_engine import (
    evaluate_fascicolo
)



documents = [

    {

        "document_type":
            "visura_catastale",

        "extraction_confidence":
            0.95

    }

]



missing_documents = [

    {

        "document_type":
            "visura_ipotecaria",

        "reason":
            "Necessaria per verificare ipoteche."

    }

]



cross_checks = [

    {

        "category":
            "proprietà",

        "severity":
            "high",

        "title":
            "Disallineamento intestatario",

        "message":
            "Il soggetto della visura non coincide con quello dell'atto."

    }

]



issues = evaluate_fascicolo(

    documents,

    missing_documents,

    cross_checks

)



result = prioritize_issues(

    issues

)



for key, values in result.items():

    print("\n======", key.upper(), "======")

    for issue in values:

        print(

            issue.title

        )