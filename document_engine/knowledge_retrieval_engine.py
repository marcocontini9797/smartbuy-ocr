"""
SmartBuy Knowledge Retrieval Engine v2

Recupera dalla Property Knowledge Base
solo il contesto pertinente alla richiesta.

NON:
- rilegge PDF
- esegue OCR
- riesegue extraction
- modifica la Knowledge Base

Serve come livello di retrieval
per Snapshot, UI e futuro LLM.
"""


from __future__ import annotations


from typing import Any





# ==================================================
# DOMAIN DEFINITIONS
# ==================================================


DOMAIN_KEYWORDS = {

    "ownership": [
        "proprietà",
        "proprieta",
        "proprietario",
        "proprietari",
        "intestatario",
        "intestatari",
        "venditore",
        "venditori",
        "acquirente",
        "titolarità",
        "titolarita",
        "atto",
        "rogito",
        "provenienza",
    ],

    "cadastral": [
        "catasto",
        "catastale",
        "visura",
        "planimetria",
        "foglio",
        "particella",
        "subalterno",
        "rendita",
        "categoria catastale",
    ],

    "urbanistic": [
        "urbanistica",
        "urbanistico",
        "edilizia",
        "edilizio",
        "conformità",
        "conformita",
        "abuso",
        "cila",
        "scia",
        "permesso",
        "sanatoria",
    ],

    "energy": [
        "energia",
        "energetico",
        "energetica",
        "ape",
        "epgl",
        "classe energetica",
        "prestazione energetica",
    ],

    "mortgage": [
        "ipoteca",
        "ipoteche",
        "ipotecaria",
        "gravame",
        "gravami",
        "vincolo",
        "vincoli",
    ],

}





FACT_DOMAIN_MAP = {

    "owner": "ownership",
    "owners": "ownership",
    "intestatario": "ownership",
    "intestatari": "ownership",
    "venditore": "ownership",

    "foglio": "cadastral",
    "particella": "cadastral",
    "subalterno": "cadastral",
    "rendita": "cadastral",
    "rendita_catastale": "cadastral",
    "categoria_catastale": "cadastral",

    "energy_class": "energy",
    "classe_energetica": "energy",
    "epgl": "energy",

}





ISSUE_DOMAIN_MAP = {

    "ownership_conflict": "ownership",

    "cadastral_conflict": "cadastral",

    "urbanistic_conflict": "urbanistic",

    "energy_conflict": "energy",

    "mortgage_conflict": "mortgage",
    "mortgage_issue": "mortgage",

}





# ==================================================
# QUERY CLASSIFICATION
# ==================================================


def detect_query_domains(

    query: str | None

) -> list[str]:

    """
    Determina gli ambiti immobiliari
    rilevanti per la domanda.
    """


    if not query:

        return []


    text = query.lower().strip()


    domains = []


    for domain, keywords in DOMAIN_KEYWORDS.items():

        if any(

            keyword in text

            for keyword in keywords

        ):

            domains.append(domain)


    return domains





# ==================================================
# FACT DOMAIN
# ==================================================


def get_fact_domain(

    fact

) -> str | None:


    field = (

        fact.field

        or ""

    ).lower()


    if field in FACT_DOMAIN_MAP:

        return FACT_DOMAIN_MAP[field]


    for key, domain in FACT_DOMAIN_MAP.items():

        if key in field:

            return domain


    return None





# ==================================================
# ISSUE DOMAIN
# ==================================================


def get_issue_domain(

    issue

) -> str | None:


    issue_type = (

        issue.issue_type

        or ""

    ).lower()


    if issue_type in ISSUE_DOMAIN_MAP:

        return ISSUE_DOMAIN_MAP[issue_type]


    return None





# ==================================================
# RETRIEVAL ENGINE
# ==================================================


class KnowledgeRetrievalEngine:


    def __init__(

        self,

        knowledge_engine

    ):

        self.knowledge_engine = knowledge_engine





    # ==============================================
    # FULL CONTEXT
    # ==============================================


    def retrieve_full_context(

        self,

        property_id: int

    ) -> dict[str, Any]:

        """
        Recupera l'intera Knowledge Base.

        Utile per:
        - snapshot generale
        - report complessivo
        - debug

        Non rianalizza documenti.
        """


        kb = self.knowledge_engine.get_property(

            property_id

        )


        if kb is None:

            return {

                "property_id": property_id,

                "facts": [],

                "issues": [],

                "evidence": [],

                "retrieval": {

                    "mode": "full",

                    "domains": []

                }

            }


        return {

            "property_id":

                property_id,


            "facts": [

                fact.model_dump()

                for fact in kb.facts

            ],


            "issues": [

                issue.model_dump()

                for issue in kb.issues

            ],


            "evidence": [

                evidence.model_dump()

                for evidence in kb.evidence

            ],


            "retrieval": {

                "mode":

                    "full",

                "domains":

                    []

            }

        }





    # ==============================================
    # SELECTIVE CONTEXT
    # ==============================================


    def retrieve_property_context(

        self,

        property_id: int,

        query: str | None = None

    ) -> dict[str, Any]:

        """
        Recupera solo il contesto
        pertinente alla domanda.

        Se la domanda non identifica
        un dominio specifico,
        restituisce il contesto completo.
        """


        kb = self.knowledge_engine.get_property(

            property_id

        )


        if kb is None:

            return {

                "property_id":

                    property_id,

                "query":

                    query,

                "facts":

                    [],

                "issues":

                    [],

                "evidence":

                    [],

                "retrieval": {

                    "mode":

                        "empty",

                    "domains":

                        []

                }

            }



        domains = detect_query_domains(

            query

        )



        # Nessun dominio riconosciuto:
        # meglio fornire il contesto completo
        # che scartare informazioni utili.

        if not domains:

            result = self.retrieve_full_context(

                property_id

            )


            result["query"] = query

            result["retrieval"] = {

                "mode":

                    "full_fallback",

                "domains":

                    []

            }


            return result





        # ------------------------------------------
        # FILTER FACTS
        # ------------------------------------------


        selected_facts = [

            fact

            for fact in kb.facts

            if get_fact_domain(fact) in domains

        ]





        # ------------------------------------------
        # FILTER ISSUES
        # ------------------------------------------


        selected_issues = [

            issue

            for issue in kb.issues

            if get_issue_domain(issue) in domains

        ]





        # ------------------------------------------
        # COLLECT LINKED EVIDENCE IDS
        # ------------------------------------------


        evidence_ids = set()



        for fact in selected_facts:

            evidence_ids.update(

                fact.evidence_ids

            )



        for issue in selected_issues:

            evidence_ids.update(

                issue.evidence_ids

            )





        # ------------------------------------------
        # RETRIEVE ONLY LINKED EVIDENCE
        # ------------------------------------------


        selected_evidence = [

            evidence

            for evidence in kb.evidence

            if evidence.id in evidence_ids

        ]





        return {

            "property_id":

                property_id,


            "query":

                query,


            "facts": [

                fact.model_dump()

                for fact in selected_facts

            ],


            "issues": [

                issue.model_dump()

                for issue in selected_issues

            ],


            "evidence": [

                evidence.model_dump()

                for evidence in selected_evidence

            ],


            "retrieval": {

                "mode":

                    "selective",

                "domains":

                    domains,

                "facts_found":

                    len(selected_facts),

                "issues_found":

                    len(selected_issues),

                "evidence_found":

                    len(selected_evidence)

            }

        }