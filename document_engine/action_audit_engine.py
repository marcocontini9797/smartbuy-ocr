"""
SmartBuy Action Audit Engine v1

Registra lo storico delle
azioni operative agente.
"""


from __future__ import annotations



from core.action_models import ActionItem



from core.audit_models import ActionAuditEvent





def create_audit_event(

    action: ActionItem,

    action_type: str,

    actor_id: str | None = None,

    previous_status: str | None = None,

    previous_priority: str | None = None

):

    """
    Crea evento audit
    relativo ad una action.
    """



    return ActionAuditEvent(

        action_id=action.id,


        action_type=action_type,


        source_type=action.source_type,


        source_reference=action.source_reference,


        actor_id=actor_id,


        previous_status=previous_status,


        new_status=action.status,


        previous_priority=previous_priority,


        new_priority=action.priority,


        metadata={

            "title":

                action.title

        }

    )