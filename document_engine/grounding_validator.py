"""
SmartBuy Grounding Validator v1

Controlla che le risposte LLM
siano supportate dal contesto.
"""


from __future__ import annotations





class GroundingValidator:



    def validate(

        self,

        response: dict,

        context

    ):


        sources = context.sources


        grounded = True



        unsupported = []



        for claim in response.get(

            "claims",

            []

        ):


            if claim.get(

                "source_required"

            ) and not sources:


                grounded = False


                unsupported.append(

                    claim["text"]

                )



        return {

            "grounded": grounded,

            "unsupported_claims":

                unsupported

        }