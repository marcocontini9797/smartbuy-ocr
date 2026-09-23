from document_engine.knowledge_engine import KnowledgeEngine


from core.knowledge_models import (

    KnowledgeFact,

    KnowledgeIssue

)





engine = KnowledgeEngine()





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





engine.add_issue(

    16,

    KnowledgeIssue(

        id="ISSUE001",

        property_id=16,

        issue_type="ownership_conflict",

        severity="high",

        title="Disallineamento intestatario"

    )

)





kb = engine.get_property(16)





print(

    kb.model_dump_json(

        indent=2

    )

)