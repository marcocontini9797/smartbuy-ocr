"""
SmartBuy Issue Rules Engine v1

Libreria decisionale per problemi immobiliari.

Trasforma un tipo di problema in:

- categoria
- gravità
- impatto commerciale
- azione consigliata
- priorità agente
"""


from __future__ import annotations





# ==================================================
# ISSUE RULE DATABASE
# ==================================================


ISSUE_RULES = {


    # ==============================================
    # PROPRIETÀ
    # ==============================================


    "ownership_conflict": {


        "category":

            "ownership",


        "severity":

            "high",


        "impact":

            "Può bloccare la vendita fino alla verifica della titolarità dell'immobile.",


        "recommended_action":

            "Verificare proprietà, intestazioni e documentazione del trasferimento.",


        "priority":

            "high"

    },





    "missing_owner_verification": {


        "category":

            "ownership",


        "severity":

            "high",


        "impact":

            "Non consente di confermare chi può disporre dell'immobile.",


        "recommended_action":

            "Richiedere documentazione aggiornata sulla proprietà.",


        "priority":

            "high"

    },





    # ==============================================
    # DOCUMENTAZIONE
    # ==============================================


    "missing_document": {


        "category":

            "documentation",


        "severity":

            "medium",


        "impact":

            "Rallenta la preparazione del fascicolo immobiliare.",


        "recommended_action":

            "Richiedere il documento mancante al proprietario.",


        "priority":

            "medium"

    },





    "document_review": {


        "category":

            "documentation",


        "severity":

            "medium",


        "impact":

            "Il documento necessita di verifica prima della pubblicazione.",


        "recommended_action":

            "Effettuare controllo manuale del documento.",


        "priority":

            "medium"

    },





    # ==============================================
    # CATASTO
    # ==============================================


    "cadastral_conflict": {


        "category":

            "cadastral",


        "severity":

            "high",


        "impact":

            "Possibile difformità catastale che può rallentare la vendita.",


        "recommended_action":

            "Confrontare dati catastali, planimetria e stato reale dell'immobile.",


        "priority":

            "high"

    },





    # ==============================================
    # URBANISTICA
    # ==============================================


    "urbanistic_conflict": {


        "category":

            "urbanistic",


        "severity":

            "high",


        "impact":

            "Possibili problemi di conformità edilizia.",


        "recommended_action":

            "Richiedere verifica urbanistica tramite tecnico abilitato.",


        "priority":

            "high"

    },





    # ==============================================
    # ENERGIA
    # ==============================================


    "energy_conflict": {


        "category":

            "energy",


        "severity":

            "low",


        "impact":

            "Informazione energetica non completamente verificata.",


        "recommended_action":

            "Controllare APE e dati energetici dichiarati.",


        "priority":

            "low"

    }

}





# ==================================================
# GET RULE
# ==================================================


def get_issue_rule(

    issue_type: str

) -> dict:


    return ISSUE_RULES.get(

        issue_type,

        {


            "category":

                "general",


            "severity":

                "medium",


            "impact":

                "Problema da approfondire.",


            "recommended_action":

                "Effettuare verifica manuale.",


            "priority":

                "medium"

        }

    )





# ==================================================
# APPLY RULE
# ==================================================


def enrich_issue_data(

    issue_data: dict

) -> dict:


    issue_type = issue_data.get(

        "type",

        "unknown"

    )


    rule = get_issue_rule(

        issue_type

    )


    enriched = rule.copy()



    enriched.update(

        issue_data

    )



    return enriched