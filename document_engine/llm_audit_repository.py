"""
SmartBuy LLM Audit Repository v1
"""

from __future__ import annotations


from typing import Any





class LLMAuditRepository:


    def __init__(

        self,

        client

    ):

        self.client = client





    def save(

        self,

        record: dict[str, Any]

    ):


        return (

            self.client

            .table(

                "llm_audit_logs"

            )

            .insert(

                record

            )

            .execute()

        )





    def list_property_runs(

        self,

        property_id:int

    ):


        return (

            self.client

            .table(

                "llm_audit_logs"

            )

            .select("*")

            .eq(

                "property_id",

                property_id

            )

            .execute()

            .data

        )