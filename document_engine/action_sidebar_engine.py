"""
SmartBuy Action Sidebar Engine v3.3

Genera azioni operative
con evidenze e identificativi collegati.
"""


from __future__ import annotations


from core.action_models import (

    ActionSidebar,

    ActionItem

)


from .action_ranking_engine import rank_actions


from .feedback_action_mapper import (

    get_issue_actions,

    get_document_actions,

    get_fact_actions

)





def issue_to_action(issue):


    evidence = [

        e.model_dump()

        for e in issue.evidence

    ]



    evidence_ids = [

        item.get("metadata", {}).get("id")

        for item in evidence

        if item.get("metadata", {}).get("id")

    ]



    document_ids = [

        item.get("document")

        for item in evidence

        if item.get("document")

    ]



    return ActionItem(

        status="red",


        priority=issue.metadata.get(

            "priority",

            issue.severity

        ),


        title=issue.title,


        reason=issue.description,


        action_description=(

            issue.recommended_action

            or

            "Effettuare verifica manuale."

        ),


        source_type="issue",


        source_reference=issue.type,


        issue_id=getattr(

            issue,

            "id",

            None

        ),


        document_ids=document_ids,


        evidence_ids=evidence_ids,


        evidence=evidence,


        available_actions=get_issue_actions()

    )





def missing_document_to_action(document):


    return ActionItem(

        status="yellow",

        priority=document.get(

            "priority",

            "medium"

        ),


        title=(

            f"Caricare {document.get('document_type')}"

        ),


        reason=document.get(

            "reason",

            "Documento necessario."

        ),


        action_description=(

            "Richiedere il documento "

            "al proprietario."

        ),


        source_type="missing_document",


        source_reference=document.get(

            "document_type"

        ),


        resolution_target=(

            "/documents/upload?"

            f"type={document.get('document_type')}"

        ),


        available_actions=get_document_actions()

    )





def fact_to_action(fact):


    return ActionItem(

        status="green",


        priority="low",


        title=(

            f"{fact.get('name')} verificato"

        ),


        reason=(

            "Informazione estratta "

            "e verificata."

        ),


        action_description=str(

            fact.get("value")

        ),


        source_type="fact",


        source_reference=fact.get(

            "name"

        ),


        available_actions=get_fact_actions()

    )





def build_action_sidebar(

    issues=None,

    missing_documents=None,

    facts=None

):


    sidebar = ActionSidebar()



    sidebar.red = rank_actions(

        [

            issue_to_action(i)

            for i in issues or []

        ]

    )


    sidebar.yellow = rank_actions(

        [

            missing_document_to_action(d)

            for d in missing_documents or []

        ]

    )


    sidebar.green = rank_actions(

        [

            fact_to_action(f)

            for f in facts or []

        ]

    )


    return sidebar