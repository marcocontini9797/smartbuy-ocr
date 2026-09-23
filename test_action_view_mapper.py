from document_engine.action_view_mapper import action_to_view


from core.action_models import ActionItem





action = ActionItem(

    status="red",

    priority="high",

    title="Disallineamento intestatario",

    reason="Visura e atto non coincidono",

    action_description="Verificare proprietà",

    source_type="issue",

    source_reference="ownership_conflict",

    evidence=[

        {

            "document":

                "visura_demo.pdf",

            "page":

                1,

            "text":

                "Intestatario: Rossi Giovanni"

        }

    ]

)





view = action_to_view(

    action

)





print(

    view.model_dump_json(

        indent=2

    )

)