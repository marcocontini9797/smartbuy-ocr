import pytest
from fastapi import HTTPException

from api import document_routes, property_routes
from api.property_routes import NewProperty, create_property


class Query:
    def __init__(self, client, table):
        self.client, self.table_name, self.filters, self.payload, self.op = client, table, {}, None, "select"

    def select(self, *_):
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_):
        return self

    def execute(self):
        self.client.calls.append((self.op, self.table_name, self.payload, dict(self.filters)))
        if self.op == "insert":
            return type("R", (), {"data": [{"id": 99, **self.payload}]})()
        return type("R", (), {"data": self.client.rows.get(self.table_name, [])})()


class Bucket:
    def __init__(self, client):
        self.client = client

    def upload(self, path, content, options):
        if self.client.storage_fails:
            raise RuntimeError("storage down")
        self.client.uploads.append((path, content, options))

    def create_signed_url(self, path, expires):
        return {"signedURL": f"https://signed/{path}?e={expires}"}


class Storage:
    def __init__(self, client):
        self.client = client

    def from_(self, bucket):
        assert bucket == "smartbuy-documents"
        return Bucket(self.client)


class FakeClient:
    smartbuy_user_id = "user-1"

    def __init__(self, rows=None, storage_fails=False):
        self.calls, self.uploads, self.rows, self.storage_fails = [], [], rows or {}, storage_fails
        self.storage = Storage(self)

    def table(self, name):
        return Query(self, name)


def test_new_property_is_owned_by_the_signed_in_user():
    client = FakeClient()
    created = create_property(NewProperty(address="  Via Vizzani 72 ", city="Bologna", surface_m2=92), client)
    op, table, payload, _ = client.calls[0]
    assert (op, table) == ("insert", "properties")
    assert payload == {"address": "Via Vizzani 72", "city": "Bologna", "surface_m2": 92.0, "user_id": "user-1"}
    assert created["id"] == 99


def test_new_property_requires_address_and_city():
    with pytest.raises(Exception):
        NewProperty(address="", city="Bologna")


def test_original_is_stored_under_user_and_property_with_a_safe_name():
    client = FakeClient()
    path = document_routes.store_original(client, property_id=16, document_id=41, filename="Visura catastale (1).pdf",
                                          content=b"%PDF", media_type="application/pdf")
    assert path == "user-1/16/41-Visura_catastale_1_.pdf"
    assert client.uploads[0][0] == path
    assert ("update", "documents", {"storage_path": path}, {"id": 41}) in client.calls


def test_storage_failure_does_not_break_the_analysis():
    client = FakeClient(storage_fails=True)
    assert document_routes.store_original(client, property_id=1, document_id=2, filename="a.pdf", content=b"x", media_type=None) is None


def test_signed_link_only_for_documents_linked_to_the_property(monkeypatch):
    monkeypatch.setattr(document_routes, "get_property", lambda property_id, client: {"id": property_id})
    client = FakeClient(rows={"document_analyses": [{"document_id": "41"}],
                              "documents": [{"storage_path": "user-1/16/41-a.pdf", "file_name": "a.pdf"}]})
    link = document_routes.open_original(16, 41, client)
    assert link["url"].startswith("https://signed/user-1/16/41-a.pdf")
    with pytest.raises(HTTPException) as missing:
        document_routes.open_original(16, 41, FakeClient(rows={"documents": [{"storage_path": "x"}]}))
    assert missing.value.status_code == 404
