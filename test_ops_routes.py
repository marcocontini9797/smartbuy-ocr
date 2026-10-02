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
