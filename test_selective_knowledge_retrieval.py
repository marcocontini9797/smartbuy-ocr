"""
Test Selective Knowledge Retrieval

Verifica che una domanda sulla proprietà
NON recuperi informazioni energetiche inutili.
"""


import json


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





# ==================================================
# OWNERSHIP EVIDENCE
# ==================================================


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



knowledge.add_evidence(

    16,

    KnowledgeEvidence(

        id="EV002",

        document="atto_demo.pdf",

        page=3,

        text="Venditore: Bianchi Mario",

        confidence=0.97

    )

)





# ==================================================
# ENERGY EVIDENCE
# ==================================================


knowledge.add_evidence(

    16,

    KnowledgeEvidence(

        id="EV003",

        document="ape_demo.pdf",

        page=2,

        text="Classe energetica A2",

        confidence=0.99

    )

)





# ==================================================
# OWNERSHIP FACT
# ==================================================


knowledge.add_fact(

    16,

    KnowledgeFact(

        id="FACT001",

        property_id=16,

        field="owner",

        value="Rossi Giovanni",

        source_document="visura_demo.pdf",

        confidence=0.98,

        evidence_ids=[

            "EV001"

        ]

    )

)





# ==================================================
# ENERGY FACT
# ==================================================


knowledge.add_fact(

    16,

    KnowledgeFact(

        id="FACT002",

        property_id=16,

        field="energy_class",

        value="A2",

        source_document="ape_demo.pdf",

        confidence=0.99,

        evidence_ids=[

            "EV003"

        ]

    )

)





# ==================================================
# OWNERSHIP ISSUE
# ==================================================


knowledge.add_issue(

    16,

    KnowledgeIssue(

        id="ISSUE001",

        property_id=16,

        issue_type="ownership_conflict",

        severity="high",

        title="Disallineamento intestatario",

        evidence_ids=[

            "EV001",

            "EV002"

        ]

    )

)





# ==================================================
# RETRIEVAL
# ==================================================


retriever = KnowledgeRetrievalEngine(

    knowledge

)



context = retriever.retrieve_property_context(

    property_id=16,

    query="Ci sono problemi sulla proprietà?"

)





print(

    json.dumps(

        context,

        indent=2,

        ensure_ascii=False

    )

)