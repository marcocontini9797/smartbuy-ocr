"""
Test SmartBuy LLM Orchestrator v2

Pipeline completa:

Question
 ↓
Knowledge Retrieval
 ↓
LLM Context Builder
 ↓
LLM Provider
 ↓
Grounded Response Engine
 ↓
Final Answer + Citations
"""


import json


from document_engine.knowledge_engine import (
    KnowledgeEngine
)


from document_engine.knowledge_retrieval_engine import (
    KnowledgeRetrievalEngine
)


from document_engine.llm_context_builder import (
    LLMContextBuilder
)


from document_engine.llm_provider import (
    MockLLMProvider
)


from document_engine.llm_orchestrator import (
    LLMOrchestrator
)


from document_engine.grounded_response_engine import (
    GroundedResponseEngine
)


from core.knowledge_models import (
    KnowledgeIssue,
    KnowledgeEvidence
)





# ==================================================
# CREAZIONE KNOWLEDGE BASE DEMO
# ==================================================


knowledge = KnowledgeEngine()





# Evidence proprietà

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





# Issue proprietà

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
# COMPONENTI SMARTBUY
# ==================================================


retriever = KnowledgeRetrievalEngine(

    knowledge

)



builder = LLMContextBuilder()



provider = MockLLMProvider()



grounding_engine = GroundedResponseEngine()





# ==================================================
# ORCHESTRATOR
# ==================================================


assistant = LLMOrchestrator(

    retriever,

    builder,

    provider,

    grounding_engine

)





# ==================================================
# DOMANDA UTENTE
# ==================================================


response = assistant.ask(

    16,

    "Ci sono problemi sulla proprietà?"

)





# ==================================================
# OUTPUT
# ==================================================


print(

    json.dumps(

        response.model_dump(),

        indent=2,

        ensure_ascii=False

    )

)