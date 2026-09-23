from document_engine.knowledge_engine import KnowledgeEngine


from document_engine.knowledge_retrieval_engine import (

    KnowledgeRetrievalEngine

)


from core.knowledge_models import (

    KnowledgeFact,

    KnowledgeEvidence,

    KnowledgeIssue

)





knowledge = KnowledgeEngine()





knowledge.add_evidence(

    16,

    KnowledgeEvidence(

        id="EV001",

        document="visura_demo.pdf",

        page=1,

        text="Intestatario: Rossi Giovanni",

        confidence=0.98

    )

)





knowledge.add_fact(

    16,

    KnowledgeFact(

        id="FACT001",

        property_id=16,

        field="owner",

        value="Rossi Giovanni",

        confidence=0.98,

        evidence_ids=["EV001"]

    )

)





knowledge.add_issue(

    16,

    KnowledgeIssue(

        id="ISSUE001",

        property_id=16,

        issue_type="ownership_conflict",

        severity="high",

        title="Disallineamento intestatario"

    )

)





retriever = KnowledgeRetrievalEngine(

    knowledge

)





context = retriever.retrieve_property_context(

    16,

    "problemi proprietà"

)





import json



print(

    json.dumps(

        context,

        indent=2,

        ensure_ascii=False

    )

)