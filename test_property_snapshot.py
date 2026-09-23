from document_engine.property_snapshot_engine import build_snapshot



from core.models import Issue





issues = [

    Issue(

        category="ownership",

        type="ownership_conflict",

        severity="high",

        title="Disallineamento intestatario",

        description="Visura e atto non coincidono"

    )

]





documents = [

    {

        "document_type":

            "visura_catastale"

    },

    {

        "document_type":

            "atto_compravendita"

    }

]





missing = [

    {

        "document_type":

            "visura_ipotecaria"

    }

]





snapshot = build_snapshot(

    property_id=16,

    documents=documents,

    issues=issues,

    missing_documents=missing,

    actions=[

        {

            "title":

                "Verificare titolarità immobile"

        }

    ]

)





print(

    snapshot.model_dump_json(

        indent=2

    )

)