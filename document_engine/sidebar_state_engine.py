"""
SmartBuy Sidebar State Engine v1

Aggiorna lo stato operativo
delle azioni agente dopo
feedback e risoluzioni.

Gestisce:

- completamento
- riapertura
- aggiornamento stato
"""


from __future__ import annotations



from datetime import datetime, timezone



from core.action_models import ActionItem





def utc_now():

    return datetime.now(

        timezone.utc

    ).isoformat()





# ==================================================
# COMPLETE ACTION
# ==================================================


def complete_action(

    action: ActionItem,

    user_id: str | None = None

):

    """
    Segna un'azione come completata.
    """



    action.completed = True



    action.status = "green"



    action.priority = "low"



    action.metadata.update(

        {

            "resolved_at":

                utc_now(),


            "resolved_by":

                user_id

        }

    )



    return action





# ==================================================
# REOPEN ACTION
# ==================================================


def reopen_action(

    action: ActionItem,

    user_id: str | None = None

):

    """
    Riapre un'azione precedente.
    """



    action.completed = False



    action.status = "red"



    action.priority = "high"



    action.metadata.update(

        {

            "reopened_at":

                utc_now(),


            "reopened_by":

                user_id

        }

    )



    return action





# ==================================================
# SNOOZE ACTION
# ==================================================


def snooze_action(

    action: ActionItem,

    user_id: str | None = None

):

    """
    Posticipa un'azione.
    """



    action.status = "yellow"



    action.priority = "medium"



    action.metadata.update(

        {

            "snoozed_at":

                utc_now(),


            "snoozed_by":

                user_id

        }

    )



    return action