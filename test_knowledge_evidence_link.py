from document_engine.knowledge_engine import KnowledgeEngine


from core.knowledge_models import (

    KnowledgeFact,

    KnowledgeEvidence

)





engine = KnowledgeEngine()





engine.add_evidence(

    16,

    KnowledgeEvidence(

        id="EV001",

        document="visura_demo.pdf",

        page=1,

        text="Intestatario: Rossi Giovanni",

        confidence=0.98

    )

)





engine.add_fact(

    16,

    KnowledgeFact(

        id="FACT001",

        property_id=16,

        field="owner",

        value="Rossi Giovanni",

        source_document="visura_demo.pdf",

        confidence=0.98

    )

)





engine.link_fact_evidence(

    16,

    "FACT001",

    "EV001"

)





kb = engine.get_property(16)





print(

    kb.model_dump_json(

        indent=2

    )

)