"""Replaced document versions and stored OCR text (offline, fake database)."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import document_routes as routes
from api import operations_routes as ops
from api import property_routes as props
from document_engine.agent_retrieval_supabase import build_agent_context
from document_engine.superseded import (
    SupersedeError,
    current_documents,
    current_facts,
    drop_superseded,
    is_superseded,
    validate_supersede,
)

TEXT = ("La presente visura descrive l immobile censito nel comune con identificativi "
        "catastali e dati relativi alla consistenza alla categoria alla rendita e "
        "agli intestatari risultanti dagli atti disponibili alla data della richiesta.")


def doc(doc_id, kind="visura_catastale", **extra):
    return {"id": doc_id, "document_type": kind, "processing_status": "completed", "superseded_by": None, **extra}


class Store:
    """Just enough of the Supabase query builder: select/eq/in_/update/insert."""

    def __init__(self, **tables):
        self.tables = {name: [dict(r) for r in rows] for name, rows in tables.items()}
        self.updates, self.inserts, self.fail = [], [], set()

    def table(self, name):
        return Query(self, name)


class Query:
    def __init__(self, store, name):
        self.store, self.name, self.filters, self.patch, self.new = store, name, [], None, None

    def select(self, *columns):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r, c=column, v=value: str(r.get(c)) == str(v))
        return self

    def in_(self, column, values):
        wanted = {str(v) for v in values}
        self.filters.append(lambda r, c=column: str(r.get(c)) in wanted)
        return self

    def update(self, patch):
        self.patch = patch
        return self

    def insert(self, row):
        self.new = row
        return self

    def execute(self):
        if self.name in self.store.fail:
            raise RuntimeError(f"{self.name} unavailable")
        if self.new is not None:
            self.store.inserts.append((self.name, self.new))
            return SimpleNamespace(data=[self.new])
        rows = [r for r in self.store.tables.get(self.name, []) if all(f(r) for f in self.filters)]
        if self.patch is not None:
            for row in rows:
                row.update(self.patch)
            self.store.updates.append((self.name, self.patch, [r["id"] for r in rows]))
            return SimpleNamespace(data=rows)
        return SimpleNamespace(data=rows)


# --- pure helpers -------------------------------------------------------------------

def test_a_document_is_replaced_only_when_superseded_by_is_set():
    assert not is_superseded(doc(1)) and not is_superseded(doc(1, superseded_by=""))
    assert is_superseded(doc(1, superseded_by=2))


def test_current_documents_and_facts_skip_replaced_versions():
    docs = [doc(1, superseded_by=2), doc(2), doc(3, kind="ape")]
    facts = [{"fact_name": "foglio", "source_document_id": 1}, {"fact_name": "foglio", "source_document_id": 2},
             {"fact_name": "prezzo", "source_document_id": None}]
    current, kept = drop_superseded(docs, facts)
    assert [d["id"] for d in current] == [2, 3]
    assert [(f["fact_name"], f["source_document_id"]) for f in kept] == [("foglio", 2), ("prezzo", None)]
    assert [d["id"] for d in current_documents(docs)] == [2, 3]
    assert current_facts(facts, docs) == kept


def test_nothing_replaced_returns_everything_and_none_inputs_are_safe():
    docs, facts = [doc(1)], [{"source_document_id": 1}]
    assert drop_superseded(docs, facts) == (docs, facts)
    assert drop_superseded(None, None) == ([], [])


def test_the_agent_context_ignores_facts_of_a_replaced_document():
    old, new = doc(1, superseded_by=2, file_name="old.pdf"), doc(2, file_name="new.pdf")
    facts = [{"id": "f1", "fact_name": "intestatari", "fact_value": {"value": "Mario Rossi"}, "source_document_id": 1},
             {"id": "f2", "fact_name": "intestatari", "fact_value": {"value": "Anna Bianchi"}, "source_document_id": 2}]
    context = build_agent_context(property_id=1, question="chi è il proprietario?",
                                  facts=facts, documents=[old, new], provenance=[])
    assert [f["value"] for f in context["facts"]] == ["Anna Bianchi"]


@pytest.mark.parametrize("older,newer,status", [
    (None, doc(2), 404),
    (doc(1), None, 404),
    (doc(1), doc(1), 422),
    (doc(1, kind="altro"), doc(2, kind="altro"), 422),
    (doc(1), doc(2, kind="ape"), 422),
    (doc(1, kind="atto_provenienza"), doc(2, kind="atto_compravendita"), 422),
    (doc(1), doc(2, superseded_by=3), 409),
    (doc(1), doc(2, processing_status="failed"), 409),
    (doc(1, superseded_by=9), doc(2), 409),
])
def test_refused_replacements(older, newer, status):
    with pytest.raises(SupersedeError) as error:
        validate_supersede(older, newer)
    assert error.value.status_code == status


def test_replacing_again_with_the_same_version_is_accepted():
    validate_supersede(doc(1, superseded_by=2), doc(2))
    validate_supersede(doc(1), doc(2, document_type="visura"))      # alias of the same kind


# --- endpoints ----------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(routes, "get_property", lambda *a: {"id": 1})
    store = Store(documents=[
        doc(10, fascicolo_id="1", file_name="vecchia.pdf"),
        doc(11, fascicolo_id="1", file_name="nuova.pdf"),
        doc(12, kind="ape", fascicolo_id="1"),
        doc(20, fascicolo_id="2", file_name="altra-pratica.pdf"),
    ])
    return store


def replace(store, old, new):
    return routes.supersede_document(1, old, routes.SupersedeRequest(replaced_by=new), store)


def test_replacing_marks_the_old_version_and_nothing_else(api):
    result = replace(api, 10, 11)
    assert result["superseded_by"] == 11
    (table, patch, ids), = api.updates
    assert table == "documents" and ids == [10] and patch["superseded_by"] == 11 and patch["superseded_at"]
    assert {r["id"]: r["superseded_by"] for r in api.tables["documents"]} == {10: 11, 11: None, 12: None, 20: None}


def test_restoring_clears_the_mark(api):
    replace(api, 10, 11)
    assert routes.restore_document(1, 10, api) == {"document_id": 10, "superseded_by": None}
    assert all(r["superseded_by"] is None for r in api.tables["documents"])


@pytest.mark.parametrize("old,new,status", [
    (10, 12, 422),    # a visura cannot be replaced by an APE
    (10, 20, 404),    # a document of another pratica is not found here
    (10, 10, 422),
    (99, 11, 404),
])
def test_endpoint_refuses_invalid_replacements(api, old, new, status):
    with pytest.raises(HTTPException) as error:
        replace(api, old, new)
    assert error.value.status_code == status
    assert not api.updates


def test_restoring_a_document_of_another_pratica_is_not_found(api):
    with pytest.raises(HTTPException) as error:
        routes.restore_document(1, 20, api)
    assert error.value.status_code == 404


def test_database_failure_is_a_502_not_a_silent_success(api):
    api.fail.add("documents")
    with pytest.raises(HTTPException) as error:
        replace(api, 10, 11)
    assert error.value.status_code == 502


# --- the checks no longer see a replaced version -------------------------------------------

def test_cross_validation_sources_exclude_the_replaced_version(monkeypatch):
    monkeypatch.setattr(ops, "get_property", lambda *a: {"id": 1})
    store = Store(
        property_facts=[{"id": "f1", "property_id": 1, "fact_name": "foglio", "source_document_id": 10},
                        {"id": "f2", "property_id": 1, "fact_name": "foglio", "source_document_id": 11}],
        document_analyses=[{"property_id": 1, "document_id": "10"}, {"property_id": 1, "document_id": "11"}],
        documents=[doc(10, superseded_by=11), doc(11)], fact_provenance=[])
    _, facts, documents, _ = ops._validation_sources(1, store)
    assert [d["id"] for d in documents] == [11]
    assert [f["id"] for f in facts] == ["f2"]


def test_valuation_facts_exclude_the_replaced_version():
    store = Store(
        property_facts=[{"id": "f1", "property_id": 1, "fact_name": "superficie_commerciale_mq", "source_document_id": 10},
                        {"id": "f2", "property_id": 1, "fact_name": "superficie_commerciale_mq", "source_document_id": 11}],
        documents=[doc(10, fascicolo_id="1", superseded_by=11), doc(11, fascicolo_id="1")])
    assert [f["id"] for f in props._current_facts(store, 1)] == ["f2"]


def test_a_failing_document_lookup_keeps_the_facts_instead_of_losing_them():
    store = Store(property_facts=[{"id": "f1", "property_id": 1, "source_document_id": 10}])
    store.fail.add("documents")
    assert [f["id"] for f in props._current_facts(store, 1)] == ["f1"]


# --- stored OCR text -----------------------------------------------------------------------------

def test_ocr_text_is_attached_only_to_documents_of_the_same_type():
    store = Store(document_text_extractions=[{"document_id": 1, "raw_text": "visura"},
                                             {"document_id": 2, "raw_text": "ape"}])
    rows = [doc(1), doc(2, kind="ape"), doc(3)]
    routes._attach_ocr_text(store, rows, "visura_catastale")
    assert rows[0]["ocr_text"] == "visura"
    assert "ocr_text" not in rows[1] and "ocr_text" not in rows[2]


def test_attaching_ocr_text_survives_a_database_failure():
    store = Store()
    store.fail.add("document_text_extractions")
    rows = [doc(1)]
    routes._attach_ocr_text(store, rows, "visura_catastale")
    assert "ocr_text" not in rows[0]


def unit(sub="3", particella="34"):
    return {"comune": "Bologna", "foglio": "12", "particella": particella, "subalterno": sub, "categoria": "A/2"}


def review(store, new_ocr):
    payload = {"document_type": "visura_catastale",
               "extracted_fields": {"riferimento": unit(), "data_visura": "02/09/2025"}}
    return routes._fascicolo_review(store, 1, {"id": 12}, payload, "nuova.pdf", "a" * 64, new_ocr)


def stored(ocr):
    return Store(
        documents=[doc(10, fascicolo_id="1", file_name="vecchia.pdf",
                       extracted_fields={"riferimento": unit(), "data_visura": "13/05/2025"}),
                   doc(11, fascicolo_id="1", file_name="gia-sostituita.pdf", superseded_by=10,
                       extracted_fields={"riferimento": unit(particella="99"), "data_visura": "01/01/2020"})],
        document_text_extractions=[{"document_id": 10, "raw_text": ocr}])


def test_review_uses_the_stored_text_and_names_the_compared_document():
    summary = review(stored(f"{TEXT} data richiesta 13/05/2025"), f"{TEXT} data richiesta 02/09/2025")
    (item,) = summary["items"]                       # the already replaced visura is not compared
    assert item["existing_file_name"] == "vecchia.pdf"
    assert item["action"] == "new_version"
    assert item["open_conflicts"] == []              # the changed numbers are the two dates


def test_review_with_a_changed_surface_keeps_that_conflict_open():
    summary = review(stored(f"{TEXT} data 13/05/2025 superficie 75"), f"{TEXT} data 02/09/2025 superficie 80")
    assert "ocr_numeric_tokens" in summary["items"][0]["open_conflicts"]


def test_review_without_stored_text_still_works():
    summary = review(stored(""), None)
    assert summary["items"][0]["action"] == "new_version"


def test_a_replaced_visura_no_longer_defines_the_expected_unit():
    # Only the replaced visura (parcel 99) disagrees with the new document's parcel 34:
    # it must not make the new document look like it belongs to another unit.
    store = Store(documents=[doc(11, fascicolo_id="1", superseded_by=10,
                                 extracted_fields={"riferimento": unit(particella="99"), "data_visura": "01/01/2020"})])
    assert review(store, None) == {"compared_with": 0, "needs_review": False, "items": []}
