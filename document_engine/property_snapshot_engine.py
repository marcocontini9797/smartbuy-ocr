"""
SmartBuy Property Snapshot Engine v1

Genera il riepilogo sintetico
del fascicolo immobiliare.
"""


from __future__ import annotations


from datetime import datetime, timezone


from core.property_snapshot_models import (
    PropertySnapshot,
    SnapshotSection
)





def build_snapshot(

    property_id: int,

    documents=None,

    issues=None,

    actions=None,

    missing_documents=None

):


    documents = documents or []

    issues = issues or []

    actions = actions or []

    missing_documents = missing_documents or []



    critical_issues = [

        issue.title

        for issue in issues

        if issue.severity == "high"

    ]



    missing = [

        item.get("document_type")

        for item in missing_documents

    ]



    action_items = [

        item.get("title")

        if isinstance(item, dict)

        else item.title

        for item in actions

    ]



    analyzed_documents = [

        item.get("document_type")

        for item in documents

    ]





    if critical_issues:

        status = "attention"

        risk = "high"


    elif missing:

        status = "incomplete"

        risk = "medium"


    else:

        status = "verified"

        risk = "low"





    summary = (

        f"Fascicolo analizzato: "

        f"{len(analyzed_documents)} documenti presenti, "

        f"{len(critical_issues)} criticità rilevate "

        f"e {len(missing)} documenti mancanti."

    )





    return PropertySnapshot(

        property_id=property_id,


        status=status,


        risk_level=risk,


        summary=summary,


        last_update=datetime.now(

            timezone.utc

        ).isoformat(),



        documents_section=SnapshotSection(

            title="Documenti analizzati",

            items=analyzed_documents

        ),



        completed_section=SnapshotSection(

            title="Verifiche completate",

            items=[

                "Analisi documentale completata",

                "Estrazione informazioni effettuata"

            ]

        ),



        pending_section=SnapshotSection(

            title="Da completare",

            items=missing

        ),



        issues_section=SnapshotSection(

            title="Criticità rilevate",

            items=critical_issues

        ),



        actions_section=SnapshotSection(

            title="Azioni necessarie",

            items=action_items

        )

    )