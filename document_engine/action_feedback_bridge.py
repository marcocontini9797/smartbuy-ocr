"""
SmartBuy Action Feedback Bridge v1.2

Collega la Action Sidebar
al sistema Feedback canonico.

Versione compatibile con
il repository feedback attuale.

Target supportati:

- FACT
- EVIDENCE
- DOCUMENT

Non usa ISSUE finché non esiste
una tabella canonica.
"""


from __future__ import annotations


from typing import Any


from core.feedback_models import (

    FeedbackEvent,

    FeedbackTarget,

    FeedbackAction

)





# ==================================================
# EVIDENCE CONFIRMATION
# ==================================================


def confirm_action_evidence(

    action,

    context: dict[str, Any]

):

    """
    L'agente conferma che l'evidenza
    alla base dell'azione è corretta.
    """


    if not action.evidence_ids:

        raise ValueError(

            "L'azione non contiene evidence_ids"

        )



    evidence_id = action.evidence_ids[0]



    return FeedbackEvent(

        idempotency_key=(

            f"EVIDENCE-{evidence_id}-CONFIRM"

        ),


        tenant_id=context["tenant_id"],


        property_id=context["property_id"],


        actor_user_id=context["actor_user_id"],


        target_type=FeedbackTarget.EVIDENCE,


        target_id=evidence_id,


        expected_version="v1",


        action=FeedbackAction.CONFIRM,


        origin="USER_EXPLICIT",


        original_payload={

            "action_title":

                action.title,


            "reason":

                action.reason,


            "source":

                action.source_reference

        },


        evidence_ids=[

            evidence_id

        ],


        document_id=(

            action.document_ids[0]

            if action.document_ids

            else None

        )

    )





# ==================================================
# FACT CORRECTION
# ==================================================


def correct_fact_action(

    fact_id,

    original_fact,

    corrected_value,

    context

):

    """
    Correzione di un valore estratto.
    """



    return FeedbackEvent(

        idempotency_key=(

            f"FACT-{fact_id}-CORRECT"

        ),


        tenant_id=context["tenant_id"],


        property_id=context["property_id"],


        actor_user_id=context["actor_user_id"],


        target_type=FeedbackTarget.FACT,


        target_id=fact_id,


        expected_version="v1",


        action=FeedbackAction.CORRECT,


        origin="USER_EXPLICIT",


        original_payload=original_fact,


        corrected_payload={

            "value":

                corrected_value

        }

    )