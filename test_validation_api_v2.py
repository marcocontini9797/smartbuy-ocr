"""API and persistence contracts with fakes only: no network or database writes."""
from fastapi.testclient import TestClient

from api import operations_routes, registry_routes
from api.session import user_client
from main_api import app
from test_validation_engine_v2 import PROPERTY, doc, unit, run
from test_registry import PROSPETTO


def test_cross_validation_and_checklist_expose_the_same_c2_finding(monkeypatch):
    docs = [doc(refs=[unit("C/2", ruolo_unita="principale")])]
    findings = run(docs)
    monkeypatch.setattr(operations_routes, "_findings", lambda property_id, client: (PROPERTY, docs, findings, []))
    app.dependency_overrides[user_client] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/properties/91/cross-validation')
            checklist = client.get('/api/v1/properties/91/checklist')
        assert response.status_code == checklist.status_code == 200
        data = response.json()
        finding = next(f for f in data["findings"] if f["rule_id"] == "category_use")
        assert data["summary"]["engine_version"] == "3.1"
        assert data["agent_review"]["coverage"]["domains"]
        assert data["agent_review"]["questions"]
        assert data["agent_review"]["next_action"]["rule_id"] == "use"
        visura = next(i for i in checklist.json()["items"] if i["key"] == "visura_catastale")
        assert visura["status"] == "problem"
        assert any(i.get("finding_id") == finding["finding_id"] for i in visura["issues"])
    finally:
        app.dependency_overrides.clear()


def test_sandbox_completion_never_creates_documents_facts_or_originals(monkeypatch):
    recorded = []
    def forbidden(*args, **kwargs):
        raise AssertionError("Sandbox attempted to persist real evidence")
    monkeypatch.setattr(registry_routes, "_save_document", forbidden)
    monkeypatch.setattr(registry_routes, "persist_document_facts", forbidden)
    monkeypatch.setattr(registry_routes, "store_original", forbidden)
    monkeypatch.setattr(registry_routes, "_record", lambda client, row: recorded.append(row) or row)
    row = {"environment": "sandbox", "property_id": 91, "cost_eur": 100, "params": {"foglio": "10", "particella": "20"}}
    registry_routes._finish_prospetto(object(), 91, {"nome": "Bologna"}, row, PROSPETTO)
    registry_routes._finish_visura(object(), 91, row, b"synthetic PDF")
    registry_routes._finish_inspection(object(), 91, {"nome": "Bologna"}, row, {})
    assert len(recorded) == 3
    assert all(r["document_id"] is None and r["cost_eur"] == 0 and r["result"]["simulated"] for r in recorded)


def test_production_completion_still_uses_existing_document_repository(monkeypatch):
    saved = []
    monkeypatch.setattr(registry_routes, "_save_document", lambda client, **values: saved.append(values) or {"id": 40})
    monkeypatch.setattr(registry_routes, "_record", lambda client, row: row)
    row = {"environment": "production", "property_id": 91, "params": {"foglio": "10", "particella": "20"}}
    result = registry_routes._finish_prospetto(object(), 91, {"nome": "Bologna"}, row, PROSPETTO)
    assert result["document_id"] == 40 and saved[0]["document_type"] == "visura_catastale"


def test_registry_cache_filters_environment(monkeypatch):
    predicates = []
    class Query:
        def table(self, name): return self
        def select(self, *args): return self
        def eq(self, key, value):
            predicates.append((key, value))
            return self
        def order(self, *args, **kwargs): return self
        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=[])
    monkeypatch.setattr(registry_routes.openapi_catasto, "environment", lambda: "production")
    registry_routes._checks(Query(), 91)
    assert ("property_id", 91) in predicates and ("environment", "production") in predicates


def test_pending_request_does_not_switch_environment(monkeypatch):
    monkeypatch.setattr(registry_routes.openapi_catasto, "environment", lambda: "production")
    monkeypatch.setattr(registry_routes, "CatastoClient", lambda **kwargs: (_ for _ in ()).throw(AssertionError("network client created")))
    registry_routes._finish_pending(object(), 91, {"environment": "sandbox"})
