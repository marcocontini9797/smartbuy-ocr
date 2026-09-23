"""
SmartBuy Grounded Response Engine v1

Aggiunge fonti e spiegazioni
alle risposte generate.
"""


from __future__ import annotations


from core.grounded_response_models import (

    GroundedResponse,

    ResponseCitation

)





class GroundedResponseEngine:


    def build(

        self,

        llm_response,

        context

    ):


        citations = [

            ResponseCitation(

                document=item["document"],

                page=item.get("page"),

                text=item["reference_text"]

            )

            for item in context.get(

                "sources",

                []

            )

        ]



        explanations = []



        for issue in context.get(

            "issues",

            []

        ):

            explanations.append(

                issue

            )



        confidence = 0



        if citations:

            confidence = 0.9



        return GroundedResponse(

            answer=llm_response.answer,


            explanation=explanations,


            citations=citations,


            confidence=confidence,


            metadata={

                "grounded": True,

                "provider":

                    llm_response.metadata.get(

                        "provider"

                    )

            }

        )