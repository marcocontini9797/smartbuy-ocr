from document_engine.memory_retrieval_engine import (
    MemoryRetrievalEngine
)





class MockMemoryRepository:


    def get_property_memory(

        self,

        property_id

    ):

        return [

            {

                "memory_type":

                    "USER_DECISION",

                "title":

                    "Proprietario confermato",

                "content":

                    {

                        "owner":

                            "Bianchi Mario"

                    }

            }

        ]





engine = MemoryRetrievalEngine(

    MockMemoryRepository()

)





memory = engine.retrieve(

    16

)





print(memory)