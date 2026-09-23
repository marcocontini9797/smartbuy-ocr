"""
SmartBuy Issue Priority Engine v1

Classifica le criticità secondo
la logica operativa di un agente immobiliare.

Categorie:

blocking
    Problemi che possono fermare
    acquisizione o vendita.

attention
    Problemi da risolvere durante
    la preparazione del fascicolo.

informational
    Informazioni utili ma non bloccanti.
"""


from __future__ import annotations


from core.models import Issue





# ==================================================
# PRIORITY RULES
# ==================================================


BLOCKING_TYPES = {


    "ownership_conflict",


    "urbanistic_conflict",


    "cadastral_conflict"


}



ATTENTION_TYPES = {


    "missing_document",


    "document_review"


}



INFORMATIONAL_TYPES = {


    "energy_conflict"


}





# ==================================================
# SINGLE ISSUE PRIORITY
# ==================================================


def classify_issue_priority(

    issue: Issue

) -> str:


    """
    Determina il livello operativo
    della criticità.
    """


    if issue.type in BLOCKING_TYPES:

        return "blocking"



    if issue.type in ATTENTION_TYPES:

        return "attention"



    if issue.type in INFORMATIONAL_TYPES:

        return "informational"





    # fallback basato sulla severità


    if issue.severity == "high":

        return "blocking"



    if issue.severity == "medium":

        return "attention"



    return "informational"





# ==================================================
# FULL PRIORITY ENGINE
# ==================================================


def prioritize_issues(

    issues: list[Issue]

) -> dict:


    result = {


        "blocking": [],


        "attention": [],


        "informational": []

    }



    for issue in issues:


        priority = classify_issue_priority(

            issue

        )


        result[priority].append(

            issue

        )



    return result