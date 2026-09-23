"""
SmartBuy Knowledge Graph Link Repository v1

Gestisce relazioni tra elementi
della Knowledge Base.

Esempi:

FACT -> EVIDENCE

ISSUE -> EVIDENCE

ISSUE -> FACT

"""


from __future__ import annotations


from typing import Any





class KnowledgeLinkRepository:


    def __init__(

        self,

        client

    ):

        self.client = client





    def create_link(

        self,

        link: dict[str, Any]

    ):


        return (

            self.client

            .table(

                "property_knowledge_links"

            )

            .upsert(

                link

            )

            .execute()

        )





    def get_source_links(

        self,

        source_type: str,

        source_id: str

    ):


        return (

            self.client

            .table(

                "property_knowledge_links"

            )

            .select("*")

            .eq(

                "source_type",

                source_type

            )

            .eq(

                "source_id",

                source_id

            )

            .execute()

            .data

        )





    def get_target_links(

        self,

        target_type: str,

        target_id: str

    ):


        return (

            self.client

            .table(

                "property_knowledge_links"

            )

            .select("*")

            .eq(

                "target_type",

                target_type

            )

            .eq(

                "target_id",

                target_id

            )

            .execute()

            .data

        )