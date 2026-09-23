from document_engine.knowledge_sync_engine import (
    KnowledgeSyncEngine
)




engine = KnowledgeSyncEngine()





old_facts = [

    {

        "id":"FACT001",

        "property_id":16,

        "field":"owner",

        "value":"Rossi Giovanni",

        "source_document":"visura_vecchia.pdf"

    }

]





new_facts = [

    {

        "id":"FACT001",

        "property_id":16,

        "field":"owner",

        "value":"Bianchi Mario",

        "source_document":"visura_nuova.pdf"

    }

]





changes = engine.compare_facts(

    old_facts,

    new_facts

)





for change in changes:

    print(

        change.model_dump_json(

            indent=2

        )

    )