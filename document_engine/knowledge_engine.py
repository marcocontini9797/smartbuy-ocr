"""
SmartBuy Knowledge Engine v2.1

Gestisce la memoria strutturata dell'immobile.

Funzioni principali:

- Property Knowledge Base
- Facts
- Evidence
- Issues
- collegamento Fact -> Evidence
- collegamento Issue -> Evidence

Questo livello rappresenta la memoria
strutturata utilizzata successivamente
da Snapshot, Retrieval e LLM.
"""


from __future__ import annotations


from core.knowledge_models import PropertyKnowledgeBase





class KnowledgeEngine:

    """
    Gestisce la Knowledge Base
    degli immobili.
    """


    def __init__(self):

        self.storage = {}





    # ==================================================
    # PROPERTY
    # ==================================================


    def create_property(

        self,

        property_id: int

    ):

        kb = PropertyKnowledgeBase(

            property_id=property_id

        )


        self.storage[property_id] = kb


        return kb





    def get_property(

        self,

        property_id: int

    ):

        return self.storage.get(

            property_id

        )





    def get_or_create_property(

        self,

        property_id: int

    ):

        kb = self.get_property(

            property_id

        )


        if kb is None:

            kb = self.create_property(

                property_id

            )


        return kb





    # ==================================================
    # EVIDENCE
    # ==================================================


    def add_evidence(

        self,

        property_id,

        evidence

    ):

        kb = self.get_or_create_property(

            property_id

        )


        # evita duplicati

        existing_ids = {

            item.id

            for item in kb.evidence

        }


        if evidence.id not in existing_ids:

            kb.evidence.append(

                evidence

            )


        return kb





    # ==================================================
    # FACTS
    # ==================================================


    def add_fact(

        self,

        property_id,

        fact

    ):

        kb = self.get_or_create_property(

            property_id

        )


        existing_ids = {

            item.id

            for item in kb.facts

        }


        if fact.id not in existing_ids:

            kb.facts.append(

                fact

            )


        return kb





    def link_fact_evidence(

        self,

        property_id,

        fact_id,

        evidence_id

    ):

        kb = self.get_property(

            property_id

        )


        if kb is None:

            raise ValueError(

                f"Knowledge Base non trovata per property_id={property_id}"

            )



        evidence_exists = any(

            evidence.id == evidence_id

            for evidence in kb.evidence

        )


        if not evidence_exists:

            raise ValueError(

                f"Evidence non trovata: {evidence_id}"

            )



        for fact in kb.facts:

            if fact.id == fact_id:

                if evidence_id not in fact.evidence_ids:

                    fact.evidence_ids.append(

                        evidence_id

                    )


                return kb



        raise ValueError(

            f"Fact non trovato: {fact_id}"

        )





    # ==================================================
    # ISSUES
    # ==================================================


    def add_issue(

        self,

        property_id,

        issue

    ):

        kb = self.get_or_create_property(

            property_id

        )


        existing_ids = {

            item.id

            for item in kb.issues

        }


        if issue.id not in existing_ids:

            kb.issues.append(

                issue

            )


        return kb





    def link_issue_evidence(

        self,

        property_id,

        issue_id,

        evidence_id

    ):

        """
        Collega una criticità
        alla prova documentale che la supporta.
        """


        kb = self.get_property(

            property_id

        )


        if kb is None:

            raise ValueError(

                f"Knowledge Base non trovata per property_id={property_id}"

            )



        evidence_exists = any(

            evidence.id == evidence_id

            for evidence in kb.evidence

        )


        if not evidence_exists:

            raise ValueError(

                f"Evidence non trovata: {evidence_id}"

            )



        for issue in kb.issues:

            if issue.id == issue_id:

                if evidence_id not in issue.evidence_ids:

                    issue.evidence_ids.append(

                        evidence_id

                    )


                return kb



        raise ValueError(

            f"Issue non trovata: {issue_id}"

        )





    # ==================================================
    # UTILITY
    # ==================================================


    def get_evidence_by_ids(

        self,

        property_id,

        evidence_ids

    ):

        """
        Recupera rapidamente
        le evidence richieste.
        """


        kb = self.get_property(

            property_id

        )


        if kb is None:

            return []


        wanted = set(

            evidence_ids

        )


        return [

            evidence

            for evidence in kb.evidence

            if evidence.id in wanted

        ]