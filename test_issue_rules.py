from document_engine.issue_rules import (
    enrich_issue_data
)



issue = {


    "type":

        "ownership_conflict",


    "title":

        "Disallineamento intestatario",


    "description":

        "Visura e atto non coincidono."

}



result = enrich_issue_data(

    issue

)



print(result)