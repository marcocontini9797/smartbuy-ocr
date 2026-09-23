from document_engine.impact_propagation_engine import (
    ImpactPropagationEngine
)


from core.knowledge_sync_models import (
    KnowledgeChange
)





class MockLinks:



    def get_source_links(

        self,

        source_type,

        source_id

    ):


        return [

            {

                "source_type":"FACT",

                "source_id":"FACT001",

                "target_type":"ISSUE",

                "target_id":"ISSUE001",

                "relation_type":"AFFECTS"

            }

        ]





engine = ImpactPropagationEngine(

    MockLinks()

)





change = KnowledgeChange(

    change_type="FACT_CHANGED",

    property_id=16,

    entity_type="FACT",

    entity_id="FACT001",

    field="owner",

    old_value="Rossi Giovanni",

    new_value="Bianchi Mario"

)





result = engine.propagate(

    change

)





print(

    result.model_dump_json(

        indent=2

    )

)