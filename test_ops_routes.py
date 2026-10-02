from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import ops_routes

app = FastAPI()
app.include_router(ops_routes.router)
client = TestClient(app)


def test_ops_disabled_without_secret(monkeypatch):
    monkeypatch.delenv("SMARTBUY_OPS_SECRET", raising=False)
    assert client.get("/ops/rag/health").status_code == 503


def test_ops_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("SMARTBUY_OPS_SECRET", "s3cret")
    assert client.get("/ops/rag/health").status_code == 403
    assert client.get("/ops/rag/health", headers={"X-SmartBuy-Ops-Token": "nope"}).status_code == 403


def test_health_counts_backlog(monkeypatch):
    from test_rag_wiring import _Client
    monkeypatch.setenv("SMARTBUY_OPS_SECRET", "s3cret")
    fake = _Client({"document_chunks": [{"document_id": 1}],
                    "document_text_extractions": [{"document_id": 1, "raw_text": "a"}, {"document_id": 2, "raw_text": "b"}]})
    monkeypatch.setattr(ops_routes, "_admin", lambda: fake)
    r = client.get("/ops/rag/health", headers={"X-SmartBuy-Ops-Token": "s3cret"})
    assert r.json() == {"documents_with_text": 2, "documents_indexed": 1, "backlog": 1}


def test_agent_feedback_requires_valid_rating_and_saves(monkeypatch):
    from api import agent_routes
    from api.session import user_client
    saved = []

    class Table:
        def insert(self, row):
            saved.append(row)
            return self

        def execute(self):
            return self

    class Fake:
        def table(self, name):
            assert name == "agent_answer_feedback"
            return Table()

    monkeypatch.setattr(agent_routes, "get_property", lambda pid, c: {"id": pid})
    app2 = FastAPI()
    app2.include_router(agent_routes.router)
    app2.dependency_overrides[user_client] = lambda: Fake()
    c = TestClient(app2)
    base = {"question": " q ", "answer": "a", "comment": "  "}
    assert c.post("/api/v1/properties/5/agent/feedback", json={**base, "rating": 0}).status_code == 422
    r = c.post("/api/v1/properties/5/agent/feedback", json={**base, "rating": -1})
    assert r.status_code == 201
    assert saved == [{"property_id": 5, "question": "q", "answer": "a", "rating": -1, "comment": None,
                      "grounded": None, "sources": []}]
