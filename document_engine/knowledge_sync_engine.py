"""
SmartBuy Knowledge Sync Engine v1

Confronta nuova conoscenza
con quella già presente.
"""


from __future__ import annotations


from core.knowledge_sync_models import (
    KnowledgeChange
)





class KnowledgeSyncEngine:


    def compare_fact(

        self,

        old_fact: dict,

        new_fact: dict

    ) -> KnowledgeChange | None:


        old_value = old_fact.get(

            "value"

        )


        new_value = new_fact.get(

            "value"

        )


        if old_value == new_value:

            return None



        return KnowledgeChange(

            change_type="FACT_CHANGED",

            property_id=new_fact["property_id"],

            entity_type="FACT",

            entity_id=new_fact.get("id"),

            field=new_fact.get("field"),

            old_value=old_value,

            new_value=new_value,

            metadata={

                "previous_source":

                    old_fact.get(

                        "source_document"

                    ),

                "new_source":

                    new_fact.get(

                        "source_document"

                    )

            }

        )





    def compare_facts(

        self,

        old_facts: list[dict],

        new_facts: list[dict]

    ) -> list[KnowledgeChange]:


        changes = []


        old_map = {

            fact["field"]: fact

            for fact in old_facts

        }


        for new_fact in new_facts:


            field = new_fact["field"]


            old_fact = old_map.get(

                field

            )


            if old_fact:

                change = self.compare_fact(

                    old_fact,

                    new_fact

                )


                if change:

                    changes.append(

                        change

                    )


            else:

                changes.append(

                    KnowledgeChange(

                        change_type="FACT_CREATED",

                        property_id=new_fact["property_id"],

                        entity_type="FACT",

                        entity_id=new_fact.get("id"),

                        field=field,

                        new_value=new_fact.get("value")

                    )

                )


        return changes