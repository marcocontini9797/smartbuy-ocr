"""
SmartBuy Property Knowledge Repository v1

Persistenza Knowledge Base su Supabase.

Gestisce:

- facts
- evidence
- issues
"""


from __future__ import annotations


from typing import Any





class KnowledgeRepository:


    def __init__(

        self,

        client

    ):

        self.client = client





    # ==========================================
    # FACTS
    # ==========================================


    def save_fact(

        self,

        fact: dict[str, Any]

    ):


        return (

            self.client

            .table("property_facts")

            .upsert(

                fact

            )

            .execute()

        )





    def get_facts(

        self,

        property_id: int

    ):


        return (

            self.client

            .table("property_facts")

            .select("*")

            .eq(

                "property_id",

                property_id

            )

            .execute()

            .data

        )





    # ==========================================
    # EVIDENCE
    # ==========================================


    def save_evidence(

        self,

        evidence: dict[str, Any]

    ):


        return (

            self.client

            .table("property_evidence")

            .upsert(

                evidence

            )

            .execute()

        )





    def get_evidence(

        self,

        property_id: int

    ):


        return (

            self.client

            .table("property_evidence")

            .select("*")

            .eq(

                "property_id",

                property_id

            )

            .execute()

            .data

        )





    # ==========================================
    # ISSUES
    # ==========================================


    def save_issue(

        self,

        issue: dict[str, Any]

    ):


        return (

            self.client

            .table("property_issues")

            .upsert(

                issue

            )

            .execute()

        )





    def get_issues(

        self,

        property_id: int

    ):


        return (

            self.client

            .table("property_issues")

            .select("*")

            .eq(

                "property_id",

                property_id

            )

            .execute()

            .data

        )