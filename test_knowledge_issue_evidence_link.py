"""
Test Knowledge Issue -> Evidence Linking
"""


from document_engine.knowledge_engine import KnowledgeEngine


from core.knowledge_models import (

    KnowledgeFact,

    KnowledgeEvidence,

    KnowledgeIssue

)





engine = KnowledgeEngine()





# ==================================================
# EVIDENCE VISURA
# ==================================================


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





# ==================================================
# EVIDENCE ATTO
# ==================================================


engine.add_evidence(

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
# FACT
# ==================================================


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





# ==================================================
# ISSUE
# ==================================================


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



engine.link_issue_evidence(

    16,

    "ISSUE001",

    "EV001"

)



engine.link_issue_evidence(

    16,

    "ISSUE001",

    "EV002"

)





# ==================================================
# OUTPUT
# ==================================================


kb = engine.get_property(

    16

)



print(

    kb.model_dump_json(

        indent=2

    )

)