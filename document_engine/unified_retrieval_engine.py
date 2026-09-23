"""
SmartBuy Unified Retrieval Engine v1

Unisce:

Knowledge Base
+
Agent Memory
"""


from __future__ import annotations





class UnifiedRetrievalEngine:


    def __init__(

        self,

        knowledge_retriever,

        memory_retriever

    ):

        self.knowledge_retriever = knowledge_retriever

        self.memory_retriever = memory_retriever





    def retrieve(

        self,

        property_id:int,

        question:str

    ):


        knowledge = (

            self.knowledge_retriever

            .retrieve_property_context(

                property_id,

                question

            )

        )


        memory = (

            self.memory_retriever

            .retrieve(

                property_id

            )

        )


        knowledge["memory"] = memory


        return knowledge