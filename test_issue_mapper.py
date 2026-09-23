from document_engine.issue_mapper import (
    map_issue_list,
    debug_print_issues
)



raw_issues = [

    {

        "category":

            "ownership",


        "type":

            "ownership_conflict",


        "severity":

            "high",


        "title":

            "Disallineamento intestatario",


        "description":

            "Il soggetto della visura non coincide con quello dell'atto.",


        "impact":

            "Possibile blocco della vendita fino alla verifica della titolarità.",


        "recommended_action":

            "Richiedere verifica della proprietà e documentazione aggiornata.",


        "evidence":

            [

                {

                    "document":

                        "visura_demo.pdf",

                    "page":

                        1,

                    "text":

                        "Intestatario: Rossi Giovanni",

                    "confidence":

                        0.98

                },

                {

                    "document":

                        "atto_demo.pdf",

                    "page":

                        3,

                    "text":

                        "Venditore: Bianchi Mario",

                    "confidence":

                        0.97

                }

            ]

    }

]



issues = map_issue_list(

    raw_issues

)



debug_print_issues(

    issues

)