from document_engine.action_ranking_engine import rank_actions

from core.action_models import ActionItem





actions = [

    ActionItem(

        status="red",

        priority="high",

        title="Verificare titolarità immobile",

        reason="Conflitto intestatari",

        action_description="Controllare atto",

        source_type="issue",

        source_reference="ownership_conflict"

    ),


    ActionItem(

        status="yellow",

        priority="medium",

        title="Caricare visura ipotecaria",

        reason="Documento mancante",

        action_description="Richiedere documento",

        source_type="missing_document",

        source_reference="missing_document"

    ),


    ActionItem(

        status="green",

        priority="low",

        title="Classe energetica verificata",

        reason="Dato presente",

        action_description="A2",

        source_type="fact",

        source_reference="energy_conflict"

    )

]





result = rank_actions(

    actions

)





for action in result:

    print(

        action.title,

        "->",

        action.metadata["action_priority_score"]

    )