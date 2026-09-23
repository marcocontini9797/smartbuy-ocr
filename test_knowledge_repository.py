from integrations.supabase.knowledge_repository import (
    KnowledgeRepository
)




class MockTable:


    def __init__(self):

        self.data = []



    def upsert(self, value):

        self.data.append(value)

        return self



    def select(self, value):

        return self



    def eq(self, field, value):

        return self



    def execute(self):

        class Result:

            data = self.data

        return Result()




class MockSupabase:


    def __init__(self):

        self.tables = {}



    def table(self, name):

        if name not in self.tables:

            self.tables[name] = MockTable()

        return self.tables[name]





client = MockSupabase()



repo = KnowledgeRepository(

    client

)



repo.save_fact(

    {

        "id":"FACT001",

        "property_id":16,

        "field":"owner",

        "value":"Rossi Giovanni",

        "confidence":0.98

    }

)



print(

    client.tables["property_facts"].data

)