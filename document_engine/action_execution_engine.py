"""
SmartBuy Action Execution Engine v1

Orchestratore principale
delle azioni agente.

Flusso:

ActionItem
    |
    ↓
FeedbackEvent
    |
    ↓
FeedbackSubmission
    |
    ↓
FeedbackReceipt
"""


from __future__ import annotations



from core.action_models import ActionItem



from .action_click_handler import (

    create_feedback_event

)



from .feedback_submission import (

    submit_feedback

)





def execute_action(

    action_item: ActionItem,

    feedback_action: str,

    repository,

    tenant_id: str,

    property_id: int,

    actor_user_id: str,

    actor_role: str = "DOMAIN_EXPERT"

):

    """
    Esegue un'azione proveniente
    dalla sidebar agente.
    """



    # 1.
    # Creazione evento feedback


    event = create_feedback_event(

        action_item,

        feedback_action,

        tenant_id,

        property_id,

        actor_user_id

    )



    # 2.
    # Submission al sistema feedback


    receipt = submit_feedback(

        event,

        repository,

        actor_role=actor_role

    )



    return receipt