"""
SmartBuy LLM Context Builder v2

Trasforma retrieval + memoria
in contesto pronto per LLM.
"""


from __future__ import annotations


from core.llm_context_models import (

    LLMContextPack,

    LLMSource

)





class LLMContextBuilder:


    def build(

        self,

        retrieved_context: dict

    ) -> LLMContextPack:


        facts = [

            f"{item['field']}: {item['value']}"

            for item in retrieved_context.get(

                "facts",

                []

            )

        ]



        issues = [

            f"{item['title']} (priorità {item['severity']})"

            for item in retrieved_context.get(

                "issues",

                []

            )

        ]



        sources = [

            LLMSource(

                evidence_id=item.get("id"),

                document_id=item.get("document_id"),

                document=item["document"],

                page=item.get("page"),

                reference_text=item["text"],

                confidence=item.get("confidence")

            )

            for item in retrieved_context.get(

                "evidence",

                []

            )

        ]



        if issues:

            summary = (

                f"Sono state rilevate "

                f"{len(issues)} criticità "

                "nel fascicolo."

            )

        else:

            summary = (

                "Non risultano criticità "

                "nel contesto analizzato."

            )



        return LLMContextPack(

            property_id=retrieved_context["property_id"],

            user_query=retrieved_context.get("query"),

            summary=summary,

            facts=facts,

            fact_records=retrieved_context.get(

                "facts",

                []

            ),

            issues=issues,

            issue_records=retrieved_context.get(

                "issues",

                []

            ),

            missing_information=retrieved_context.get(

                "missing_information",

                []

            ),

            sources=sources,


            # NUOVO

            memory=retrieved_context.get(

                "memory",

                []

            ),


            metadata={

                "retrieval":

                    retrieved_context.get(

                        "retrieval",

                        {}

                    )

            }

        )