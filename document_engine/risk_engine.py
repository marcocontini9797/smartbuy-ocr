"""
SmartBuy Document Engine - Risk Engine v2

Trasforma le note di incertezza generate
durante l'estrazione documentale in una
analisi strutturata dei rischi.

Output:

critical:
    problemi potenzialmente bloccanti

warnings:
    aspetti da verificare

information:
    informazioni utili senza rischio diretto

Il modulo non modifica i dati estratti.
Produce solamente analisi.
"""

from __future__ import annotations





# ==================================================
# RISK RULES
# ==================================================


RISK_RULES = [

    {

        "id": "IPO-001",

        "keywords": [

            "mutuo",
            "ipoteca",
            "ipotecaria",
            "gravame"

        ],

        "category": "ipoteche",

        "severity": "medium",

        "level": "warnings",

        "title": "Verifica ipoteche e gravami",

        "message":
            "La presenza o assenza di ipoteche non è verificabile tramite la sola visura catastale.",

        "action":
            "Richiedere visura ipotecaria aggiornata."

    },


    {

        "id": "CAT-001",

        "keywords": [

            "interno",
            "disallineamento",
            "non presente nei dati catastali",
            "allineamento"

        ],

        "category": "catasto",

        "severity": "low",

        "level": "warnings",

        "title":
            "Verifica identificativo immobile",

        "message":
            "Sono presenti elementi dell'indirizzo che richiedono verifica di coerenza.",

        "action":
            "Confrontare con planimetria catastale e documentazione tecnica."

    },


    {

        "id": "URB-001",

        "keywords": [

            "conformità urbanistica",
            "urbanistica",
            "titoli edilizi",
            "cila",
            "scia"

        ],

        "category": "urbanistica",

        "severity": "medium",

        "level": "warnings",

        "title":
            "Verifica conformità urbanistica",

        "message":
            "La conformità urbanistica richiede documentazione edilizia specifica.",

        "action":
            "Richiedere titoli edilizi e verifica tecnica."

    },


    {

        "id": "ENE-001",

        "keywords": [

            "classe energetica",
            "ape",
            "prestazione energetica",
            "riscaldamento"

        ],

        "category": "energia",

        "severity": "low",

        "level": "information",

        "title":
            "Informazione energetica presente",

        "message":
            "Sono presenti dati energetici che devono essere verificati tramite APE.",

        "action":
            "Confrontare con attestato di prestazione energetica."

    },


    {

        "id": "DOC-001",

        "keywords": [

            "non verificabile",
            "richiede verifica",
            "non tipiche",
            "fuori ambito"

        ],

        "category": "documento",

        "severity": "low",

        "level": "information",

        "title":
            "Informazione fuori ambito documento",

        "message":
            "Il documento contiene informazioni appartenenti ad altre verifiche documentali.",

        "action":
            "Verificare tramite documentazione dedicata."

    }

]





# ==================================================
# RULE MATCH
# ==================================================


def match_rule(

    note: str,

    rule: dict

) -> bool:


    text = note.lower()


    return any(

        keyword.lower() in text

        for keyword in rule["keywords"]

    )





# ==================================================
# RISK ANALYSIS GENERATOR
# ==================================================


def generate_risk_analysis(

    extraction_result: dict

) -> dict:


    analysis = {


        "critical": [],


        "warnings": [],


        "information": []

    }



    fields = extraction_result.get(

        "fields",

        {}

    )



    notes = fields.get(

        "note_incertezza",

        []

    )



    if not notes:

        return analysis





    generated_ids = set()



    for note in notes:


        note_text = str(note)



        for rule in RISK_RULES:


            if not match_rule(

                note_text,

                rule

            ):

                continue



            if rule["id"] in generated_ids:

                continue



            risk = {


                "id":
                    rule["id"],


                "category":
                    rule["category"],


                "severity":
                    rule["severity"],


                "title":
                    rule["title"],


                "message":
                    rule["message"],


                "action":
                    rule["action"],


                "source":
                    note_text

            }



            analysis[rule["level"]].append(

                risk

            )



            generated_ids.add(

                rule["id"]

            )


            break



    return analysis





# ==================================================
# SUMMARY
# ==================================================


def risk_summary(

    analysis: dict

) -> dict:


    return {


        "critical":

            len(

                analysis.get(

                    "critical",

                    []

                )

            ),


        "warnings":

            len(

                analysis.get(

                    "warnings",

                    []

                )

            ),


        "information":

            len(

                analysis.get(

                    "information",

                    []

                )

            )

    }