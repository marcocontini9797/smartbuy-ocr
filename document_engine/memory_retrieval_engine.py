"""
SmartBuy Memory Retrieval Engine v1

Recupera la memoria storica
dell'immobile.
"""


from __future__ import annotations





class MemoryRetrievalEngine:


    def __init__(

        self,

        memory_repository

    ):

        self.memory_repository = memory_repository





    def retrieve(

        self,

        property_id: int

    ):


        memories = self.memory_repository.get_property_memory(

            property_id

        )


        return memories