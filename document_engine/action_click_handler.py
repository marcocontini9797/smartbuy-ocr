"""
SmartBuy Action Click Handler v1

Gestisce il click dell'agente
sulle azioni presenti nella sidebar.

Responsabilità:

ActionItem
    +
Feedback button
        |
        ↓
FeedbackEvent
"""


from __future__ import annotations



from hashlib import sha256



from core.action_models import ActionItem



from core.feedback_models import (

    FeedbackEvent,

    FeedbackAction,

    FeedbackTarget

)





# ==================================================
# ACTION MAPPING
# ==================================================


def map_feedback_action(

    action: str

):

    """
    Converte il valore ricevuto
    dalla UI nell'enum FeedbackAction.
    """


    try:

        return FeedbackAction(

            action

        )


    except ValueError:

        raise ValueError(

            f"Azione feedback non supportata: {action}"

        )





# ==================================================
# TARGET RESOLUTION
# ==================================================


def resolve_target_type(

    item: ActionItem

):

    """
    Determina il tipo di oggetto
    a cui applicare il feedback.
    """



    if item.source_type == "issue":

        return FeedbackTarget.ISSUE



    if item.source_type == "fact":

        return FeedbackTarget.FACT



    if item.source_type == "missing_document":

        return FeedbackTarget.MISSING_INFO



    return FeedbackTarget.RECOMMENDATION





# ==================================================
# CREATE EVENT
# ==================================================


def create_feedback_event(

    item: ActionItem,

    feedback_action: str,

    tenant_id: str,

    property_id: int,

    actor_user_id: str

):

    """
    Crea un FeedbackEvent
    partendo da una Action Sidebar.
    """



    action = map_feedback_action(

        feedback_action

    )



    target_type = resolve_target_type(

        item

    )



    target_id = (

        item.source_reference

        or item.id

    )



    original_payload = {

        "title":

            item.title,


        "reason":

            item.reason,


        "action_description":

            item.action_description,


        "source_type":

            item.source_type

    }





    return FeedbackEvent(

        idempotency_key=(

            sha256(

                (

                    item.id

                    +

                    feedback_action

                ).encode()

            ).hexdigest()

        ),


        tenant_id=tenant_id,


        property_id=property_id,


        actor_user_id=actor_user_id,


        target_type=target_type,


        target_id=target_id,


        expected_version=(

            item.id

        ),


        action=action,


        origin="USER_EXPLICIT",


        original_payload=original_payload,


        evidence_ids=item.evidence_ids,


        document_id=(

            item.document_ids[0]

            if item.document_ids

            else None

        )

    )