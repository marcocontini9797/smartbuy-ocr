"""
SmartBuy Feedback State Bridge v1

Collega gli eventi feedback
allo stato della sidebar.

Flusso:

FeedbackEvent
        |
        ↓
FeedbackAction
        |
        ↓
Sidebar State Engine
        |
        ↓
ActionItem aggiornato
"""


from __future__ import annotations



from core.action_models import ActionItem



from core.feedback_models import FeedbackAction



from .sidebar_state_engine import (

    complete_action,

    reopen_action,

    snooze_action

)





def apply_feedback_to_action(

    action: ActionItem,

    feedback_action: FeedbackAction,

    user_id: str | None = None

):

    """
    Applica un feedback
    allo stato della sidebar.
    """



    if feedback_action == FeedbackAction.RESOLVED:

        return complete_action(

            action,

            user_id

        )



    if feedback_action == FeedbackAction.REOPEN:

        return reopen_action(

            action,

            user_id

        )



    if feedback_action == FeedbackAction.SNOOZE:

        return snooze_action(

            action,

            user_id

        )



    # CONFIRM / ACCEPT / CORRECT
    # non cambiano lo stato operativo
    # ma vengono registrati nel feedback system


    return action