"""
SmartBuy Agent Service v1

Entry point unico dell'agente.
"""

from __future__ import annotations


from core.agent_service_models import (

    AgentAnswer

)





class SmartBuyAgentService:



    def __init__(

        self,

        retrieval,

        llm_gateway,

        evaluator=None

    ):


        self.retrieval = retrieval

        self.llm_gateway = llm_gateway

        self.evaluator = evaluator





    def ask(

        self,

        property_id:int,

        question:str,

        user_id:str | None = None

    ):


        # 1. Recupero conoscenza


        context = self.retrieval.retrieve(

            property_id,

            question

        )





        # 2. Chiamata LLM


        response = self.llm_gateway.complete(

            task="property_analysis",

            context=context,

            property_id=property_id,

            user_query=question

        )





        # 3. Risposta servizio


        return AgentAnswer(

            property_id=property_id,

            answer=response.answer,

            confidence=response.confidence,

            grounded=response.metadata.get(

                "grounded",

                True

            ),

            sources=context.get(

                "sources",

                []

            ),

            risk_level=context.get(

                "risk_level"

            )

        )