"""
SmartBuy Action Ranking Engine v1

Ordina le azioni della sidebar
secondo l'impatto operativo
per l'agente immobiliare.
"""


from __future__ import annotations


from core.action_models import ActionItem





# ==================================================
# PRIORITY SCORES
# ==================================================


ACTION_SCORES = {


    # problemi che possono bloccare la vendita

    "ownership_conflict": 100,


    "urbanistic_conflict": 95,


    "cadastral_conflict": 90,


    # documenti importanti

    "missing_document": 70,


    "document_review": 60,


    # informazioni

    "energy_conflict": 30

}





def calculate_action_priority_score(

    action: ActionItem

):


    """
    Calcola il punteggio operativo
    della singola azione.
    """


    source = action.source_reference



    if source in ACTION_SCORES:

        return ACTION_SCORES[source]



    if action.priority == "high":

        return 80



    if action.priority == "medium":

        return 50



    return 20





# ==================================================
# RANK ACTIONS
# ==================================================


def rank_actions(

    actions: list[ActionItem]

):


    ranked = []



    for action in actions:


        score = calculate_action_priority_score(

            action

        )


        item = action.model_copy()



        item.metadata["action_priority_score"] = score



        ranked.append(

            item

        )



    return sorted(

        ranked,

        key=lambda x:

            x.metadata["action_priority_score"],

        reverse=True

    )