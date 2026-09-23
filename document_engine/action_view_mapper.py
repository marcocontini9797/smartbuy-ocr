"""
SmartBuy Action View Mapper v1

Converte gli oggetti interni
nella vista utilizzata dalla UI.
"""


from __future__ import annotations



from core.action_models import ActionItem


from core.action_view_models import SmartBuyActionView





def action_to_view(

    action: ActionItem,

    history=None

):


    return SmartBuyActionView(

        id=action.id,


        status=action.status,


        priority=action.priority,


        title=action.title,


        reason=action.reason,


        action_description=action.action_description,


        source_type=action.source_type,


        source_reference=action.source_reference,


        evidence=action.evidence,


        available_actions=[

            item.model_dump()

            for item in action.available_actions

        ],


        history=history or [],


        completed=action.completed,


        metadata=action.metadata

    )