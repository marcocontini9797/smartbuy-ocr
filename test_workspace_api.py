from fastapi.testclient import TestClient
from main_api import app
from api.session import user_client


def test_requires_session():
    client = TestClient(app)
    for path in ['/api/v1/properties', '/api/v1/properties/16', '/api/v1/properties/16/workspace']:
        assert client.get(path).status_code == 401
    response = client.post(
        '/api/v1/properties/16/documents',
        files={'file': ('ape.pdf', b'%PDF-1.4', 'application/pdf')},
    )
    assert response.status_code == 401


def test_health_and_unconfigured_agent():
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    assert client.post('/agent/ask', json={'property_id':16,'question':'test'}).status_code == 503


def test_missing_property_does_not_load_other_data():
    class EmptyClient:
        smartbuy_user_id = "user-a"
        def table(self, table):
            assert table == 'properties'
            return self
        def select(self, *args): return self
        def eq(self, *args): return self
        def limit(self, *args): return self
        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=[])
    app.dependency_overrides[user_client] = lambda: EmptyClient()
    try:
        assert TestClient(app).get('/api/v1/properties/999/workspace').status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_workspace_documents_follow_analysis_links():
    from types import SimpleNamespace
    class Query:
        def __init__(self, table): self.table_name=table
        def select(self, *args): return self
        def eq(self, field, value):
            assert self.table_name != 'documents'
            return self
        def limit(self, *args): return self
        def in_(self, field, values):
            assert self.table_name == 'documents' and field == 'id' and values == [21]
            return self
        def execute(self):
            return SimpleNamespace(data={'properties':[{'id':16}], 'document_analyses':[{'id':'a','property_id':16,'document_id':21}], 'documents':[{'id':21,'file_name':'atto.pdf'}]}.get(self.table_name,[]))
    class Client:
        smartbuy_user_id = "user-a"
        def table(self, table): return Query(table)
    app.dependency_overrides[user_client]=lambda:Client()
    try:
        response=TestClient(app).get('/api/v1/properties/16/workspace')
        assert response.status_code==200
        data=response.json()
        assert data['documents'][0]['id']==data['analyses'][0]['document_id']
        assert data['summary']['documents']==1
    finally: app.dependency_overrides.clear()


def test_account_property_queries_enforce_owner():
    from types import SimpleNamespace
    seen=[]
    class Query:
        def select(self,*a): return self
        def eq(self,k,v): seen.append((k,v)); return self
        def order(self,*a,**k): return self
        def limit(self,*a): return self
        def execute(self): return SimpleNamespace(data=[])
    class Client:
        smartbuy_user_id='verified-user'
        def table(self,name):
            assert name=='properties'
            return Query()
    app.dependency_overrides[user_client]=lambda:Client()
    try:
        client=TestClient(app)
        assert client.get('/api/v1/properties').status_code==200
        assert ('user_id','verified-user') in seen
        seen.clear()
        assert client.get('/api/v1/properties/16').status_code==404
        assert ('id',16) in seen and ('user_id','verified-user') in seen
    finally: app.dependency_overrides.clear()


def test_intelligence_uses_real_profile_risk_and_provenance():
    from types import SimpleNamespace
    rows = {
        'properties': [{'id': 16, 'user_id': 'verified-user', 'address': 'Via Test 1', 'city': 'Bologna'}],
        'document_analyses': [{'id': 31, 'property_id': 16, 'document_id': 21}],
        'documents': [{'id': 21, 'file_name': 'ape.pdf', 'processing_status': 'completed'}],
        'property_facts': [{'id': 41, 'property_id': 16, 'fact_name': 'energy_class', 'fact_value': {'value': 'A2'}, 'confidence_score': '0.98', 'verification_status': 'confirmed', 'source_type': 'document', 'source_document_id': 21, 'provenance_id': 51}],
        'fact_provenance': [{'id': 51, 'source_document': 'ape.pdf', 'source_page': 2, 'source_text': 'Classe energetica A2'}],
    }
    class Query:
        def __init__(self, name): self.name=name
        def select(self,*a): return self
        def eq(self,*a): return self
        def limit(self,*a): return self
        def in_(self,*a): return self
        def execute(self): return SimpleNamespace(data=rows[self.name])
    class Client:
        smartbuy_user_id='verified-user'
        def table(self,name): return Query(name)
    app.dependency_overrides[user_client]=lambda:Client()
    try:
        response=TestClient(app).get('/api/v1/properties/16/intelligence')
        assert response.status_code==200
        data=response.json()
        assert data['profile']['energy_certificate']['energy_class']=='A2'
        assert data['facts'][0]['provenance']['source_page']==2
        assert data['summary']['documents_analyzed']==1
        assert isinstance(data['risks'], list)
    finally: app.dependency_overrides.clear()
