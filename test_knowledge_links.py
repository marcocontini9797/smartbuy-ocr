from integrations.supabase.knowledge_link_repository import (
    KnowledgeLinkRepository
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



repo = KnowledgeLinkRepository(

    client

)





repo.create_link(

    {

        "id":"LINK001",

        "property_id":16,

        "source_type":"ISSUE",

        "source_id":"ISSUE001",

        "target_type":"EVIDENCE",

        "target_id":"EV001",

        "relation_type":"SUPPORTED_BY"

    }

)





print(

    client.tables[

        "property_knowledge_links"

    ].data

)