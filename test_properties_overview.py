from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import operations_routes
from api.session import user_client


class Q:
    def __init__(self, rows):
        self.rows, self.filters, self.in_filters = rows, {}, {}

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        self.in_filters[key] = set(values)
        return self

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        rows = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())
                and all(r.get(k) in v for k, v in self.in_filters.items())]
        return type("R", (), {"data": rows})()


class Fake:
    smartbuy_user_id = "u1"

    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Q(self.tables.get(name, []))


def app_with(tables):
    app = FastAPI()
    app.include_router(operations_routes.router)
    app.dependency_overrides[user_client] = lambda: Fake(tables)
    return TestClient(app)


def test_overview_counts_documents_and_missing_required_per_property():
    tables = {
        "properties": [{"id": 2, "user_id": "u1", "typology": "appartamento", "contract": "vendita", "property_type": "residenziale"},
                       {"id": 1, "user_id": "u1", "typology": "appartamento", "contract": "vendita", "property_type": "residenziale"},
                       {"id": 9, "user_id": "someone-else"}],
        "document_analyses": [{"property_id": 1, "document_id": 10}],
        "documents": [{"id": 10, "document_type": "visura_catastale", "file_name": "v.pdf", "extracted_fields": {}}],
        "property_facts": [],
    }
    items = {i["property_id"]: i for i in app_with(tables).get("/api/v1/properties-overview").json()["items"]}
    assert set(items) == {1, 2}                       # another user's property is never listed
    assert items[2]["documents"] == 0 and items[2]["required_present"] == 0
    assert items[1]["documents"] == 1 and items[1]["required_present"] == 1
    assert items[1]["missing_required"] == items[2]["missing_required"] - 1
    assert items[2]["tone"] == "missing"


def test_overview_of_an_empty_portfolio():
    assert app_with({"properties": []}).get("/api/v1/properties-overview").json() == {"items": []}


def test_reads_are_retried_once_then_reported(monkeypatch):
    from api import property_routes
    monkeypatch.setattr(property_routes.time, "sleep", lambda *_: None)

    class Flaky:
        def __init__(self, failures):
            self.failures, self.calls = failures, 0

        def table(self, name):
            return self

        def select(self, *_):
            return self

        def eq(self, *_):
            return self

        def execute(self):
            self.calls += 1
            if self.calls <= self.failures:
                raise ConnectionError("reset")
            return type("R", (), {"data": [{"id": 1}]})()

    once = Flaky(1)
    assert property_routes._rows(once, "property_facts", 5) == [{"id": 1}] and once.calls == 2
    twice = Flaky(5)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as err:
        property_routes._rows(twice, "property_facts", 5)
    assert err.value.status_code == 502 and twice.calls == 2
    assert property_routes._optional_rows(Flaky(5), "x", 5) == []
