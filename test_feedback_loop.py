from core.feedback_loop_models import (
    FeedbackDecision
)


from document_engine.feedback_loop_engine import (
    FeedbackLoopEngine
)





class MockMemory:



    def __init__(self):

        self.data=[]



    def save(

        self,

        item

    ):

        self.data.append(item)





class MockKnowledge:



    def __init__(self):

        self.updated=[]



    def update_fact(

        self,

        fact_id,

        value

    ):

        self.updated.append(

            {

            "id":fact_id,

            "value":value

            }

        )





memory = MockMemory()


knowledge = MockKnowledge()





engine = FeedbackLoopEngine(

    memory,

    knowledge

)





feedback = FeedbackDecision(

    property_id=16,

    target_type="FACT",

    target_id="FACT001",

    action="CORRECT",

    user_id="agent_001",

    corrected_value="Bianchi Mario",

    reason="Nuova visura disponibile"

)





result = engine.process(

    feedback

)





print("================ RESULT ================")

print(result)



print("================ MEMORY ================")

print(memory.data)



print("================ KNOWLEDGE ================")

print(knowledge.updated)