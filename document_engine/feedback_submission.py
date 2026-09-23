"""
SmartBuy Feedback Submission Adapter v1

Collega gli eventi feedback
al FeedbackService canonico.

Responsabilità:

FeedbackEvent
        |
        ↓
FeedbackService.submit()

Non contiene logica di business.
Non salva direttamente.
"""



from __future__ import annotations



from core.feedback_models import (

    FeedbackEvent,

    FeedbackReceipt

)



from .feedback_service import FeedbackService





def submit_feedback(

    event: FeedbackEvent,

    repository,

    actor_role: str = "END_USER"

) -> FeedbackReceipt:

    """
    Invia un evento feedback
    al sistema canonico SmartBuy.
    """


    service = FeedbackService(

        repository

    )


    return service.submit(

        event,

        actor_role=actor_role

    )