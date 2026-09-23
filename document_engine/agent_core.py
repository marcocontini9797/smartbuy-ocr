"""
SmartBuy Agent Core v2
"""


from __future__ import annotations


from core.agent_models import AgentResponse





class SmartBuyAgentCore:



    def __init__(

        self,

        retrieval_engine,

        context_builder,

        llm_client,

        grounding_validator

    ):


        self.retrieval_engine = retrieval_engine

        self.context_builder = context_builder

        self.llm_client = llm_client

        self.grounding_validator = grounding_validator





    def ask(

        self,

        property_id:int,

        question:str

    ):



        retrieved = (

            self.retrieval_engine.retrieve(

                property_id,

                question

            )

        )



        context = (

            self.context_builder.build(

                retrieved

            )

        )



        llm_result = (

            self.llm_client.generate(

                context

            )

        )



        validation = (

            self.grounding_validator.validate(

                llm_result,

                context

            )

        )



        return AgentResponse(

            answer=

                llm_result["answer"],


            explanation=

                llm_result.get(

                    "claims",

                    []

                ),


            sources=[

                source.model_dump()

                for source in context.sources

            ],


            memory_used=bool(

                retrieved.get(

                    "memory"

                )

            ),


            confidence=

                llm_result.get(

                    "confidence",

                    0

                ),


            metadata={

                "grounded":

                    validation["grounded"],

                "unsupported_claims":

                    validation["unsupported_claims"]

            }

        )