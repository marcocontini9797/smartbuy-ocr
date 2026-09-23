"""
SmartBuy LLM Orchestrator v2

Pipeline completa:

Retrieval
+
Context Builder
+
LLM
+
Grounding
"""


from core.llm_models import LLMRequest





class LLMOrchestrator:


    def __init__(

        self,

        retriever,

        context_builder,

        provider,

        grounding_engine

    ):

        self.retriever = retriever

        self.context_builder = context_builder

        self.provider = provider

        self.grounding_engine = grounding_engine





    def ask(

        self,

        property_id: int,

        question: str

    ):


        retrieved = self.retriever.retrieve_property_context(

            property_id,

            question

        )



        context_pack = self.context_builder.build(

            retrieved

        )



        request = LLMRequest(

            property_id=property_id,

            question=question,

            context=context_pack.model_dump()

        )



        llm_response = self.provider.generate(

            request

        )



        grounded = self.grounding_engine.build(

            llm_response,

            context_pack.model_dump()

        )


        return grounded