"""Identity-aware fascicolo actions: builder, integration and upload helper (offline)."""
import hashlib
from types import SimpleNamespace

import pytest

from api import document_routes as routes
from document_engine.document_similarity import compare_documents
from document_engine.fascicolo_builder import build_fascicolo_action
from document_engine.fascicolo_integration import (
    build_fascicolo_comparisons,
    expected_units_from_documents,
    summarize_comparisons,
)


def unit(particella="34", sub="3", category="A/2", comune="Bologna"):
    return {"comune": comune, "foglio": "12", "particella": particella, "subalterno": sub, "categoria": category}


def row(doc_id, issued, *, doc_type="visura_catastale", reference=None, **fields):
    """A `documents` row as stored: extraction fields only, no OCR text."""
    body = {"riferimento": reference if reference is not None else unit(), "data_visura": issued, **fields}
    return {"id": doc_id, "document_type": doc_type, "extracted_fields": body,
            "content_sha256": hashlib.sha256(doc_id.encode()).hexdigest(), "processing_status": "completed"}


def payload(issued, *, doc_type="visura_catastale", reference=None):
    return {"document_type": doc_type,
            "extracted_fields": {"riferimento": reference if reference is not None else unit(), "data_visura": issued}}


def compare(new_payload, existing_rows, **kwargs):
    return build_fascicolo_comparisons(new_payload, new_document_id="new", filename="n.pdf",
                                       sha256="a" * 64, existing_documents=existing_rows, **kwargs)


# --- case A: an updated visura ---------------------------------------------------

def test_updated_visura_becomes_new_version_not_a_silent_add():
    (entry,) = compare(payload("02/09/2025"), [row("doc-1", "13/05/2025")])
    action = entry["action"]
    assert action["action"] == "new_version"
    assert action["previous_document_id"] == "doc-1"
    assert action["requires_review"] is True
    assert action["lineage"] == "inferred_from_unit_type_and_date"
    assert action["automatic_merge_allowed"] is False
    assert "dedotta, non dichiarata" in action["reason"]


def test_older_upload_is_reported_as_older_version():
    (entry,) = compare(payload("13/05/2025"), [row("doc-1", "02/09/2025")])
    assert entry["action"]["action"] == "older_version"


def test_municipality_written_differently_is_still_the_same_unit():
    existing = row("doc-1", "13/05/2025", reference=unit(comune="BOLOGNA (BO)"))
    (entry,) = compare(payload("02/09/2025", reference=unit(comune="Comune di Bologna")), [existing])
    assert entry["identity_resolution"]["unit_relation"] == "same_units"
    assert entry["action"]["action"] == "new_version"


# --- case B: a document of another unit ----------------------------------------------

def test_other_parcel_is_flagged_for_review_instead_of_added_silently():
    existing = [row("doc-1", "13/05/2025", reference=unit("20"))]
    (entry,) = compare(payload("02/09/2025", reference=unit("99")), existing)
    assert entry["similarity"]["status"] == "different"
    # What the builder alone used to do with that status:
    plain = build_fascicolo_action({"document_id": "new"}, similarity_result=entry["similarity"])
    assert plain["action"] == "add_document" and plain["requires_review"] is False
    assert entry["identity_resolution"]["verdict"] == "unit_outside_expected"
    assert entry["action"]["action"] == "review_unit"
    assert entry["action"]["requires_review"] is True


def test_garage_of_the_same_parcel_is_an_accessory_to_confirm():
    existing = [row("doc-1", "13/05/2025", reference=unit("20", sub="3", category="A/2"))]
    (entry,) = compare(payload("02/09/2025", reference=unit("20", sub="9", category="C/6")), existing)
    assert entry["identity_resolution"]["verdict"] == "ancillary_unit_candidate"
    assert entry["action"]["action"] == "review_unit"
    assert "pertinenza" in entry["action"]["reason"]


def test_disabling_the_expectation_still_asks_for_review():
    existing = [row("doc-1", "13/05/2025", reference=unit("20"))]
    (entry,) = compare(payload("02/09/2025", reference=unit("99")), existing, expected_units=[])
    assert entry["identity_resolution"]["verdict"] == "different_units_expectation_unknown"
    assert entry["action"]["action"] == "review_unit"


def test_cadastral_code_versus_municipality_name_is_never_called_another_unit():
    existing = [row("doc-1", "13/05/2025", reference=unit("20"))]
    code_unit = {"codice_comune": "A944", "foglio": "12", "particella": "20", "subalterno": "3"}
    (entry,) = compare(payload("02/09/2025", reference=unit("99")), existing, expected_units=[code_unit])
    assert entry["identity_resolution"]["verdict"] == "different_units_expectation_unknown"
    assert entry["identity_resolution"]["expected_unit"] == {"a": "unknown", "b": "unknown"}
    assert entry["action"]["action"] == "review_unit"


# --- same unit, other document type -----------------------------------------------------

def test_planimetria_of_the_same_unit_is_added_without_review():
    (entry,) = compare(payload("02/09/2025", doc_type="planimetria_catastale"), [row("doc-1", "13/05/2025")])
    assert entry["identity_resolution"]["verdict"] == "same_unit_different_document_types"
    assert entry["action"]["action"] == "add_document"
    assert entry["action"]["requires_review"] is False


# --- expected units ----------------------------------------------------------------------

def test_expected_units_come_from_visure_only():
    rows = [row("v1", "13/05/2025", reference=unit("20")),
            row("a1", "13/05/2025", doc_type="ape", reference=unit("77"))]
    assert expected_units_from_documents(rows) == [unit("20")]


def test_no_visura_means_no_expected_unit():
    assert expected_units_from_documents([row("a1", "13/05/2025", doc_type="ape")]) is None
    assert expected_units_from_documents([]) is None


def test_a_visura_without_references_gives_no_expectation():
    broken = {"id": "v2", "document_type": "visura_catastale", "extracted_fields": {}}
    assert expected_units_from_documents([row("v1", "13/05/2025"), broken]) is None


# --- summary -------------------------------------------------------------------------------

def test_summary_is_compact_and_never_allows_merge():
    existing = [row("doc-1", "13/05/2025"), row("doc-2", "01/01/2024", doc_type="ape")]
    summary = summarize_comparisons(compare(payload("02/09/2025"), existing))
    assert summary["compared_with"] == 2
    assert summary["needs_review"] is True
    assert {item["existing_document_id"] for item in summary["items"]} == {"doc-1", "doc-2"}
    assert all(item["automatic_merge_allowed"] is False for item in summary["items"])
    assert "similarity" not in summary["items"][0]


def test_summary_of_an_empty_fascicolo():
    assert summarize_comparisons([]) == {"compared_with": 0, "needs_review": False, "items": []}


# --- upload helper -----------------------------------------------------------------------------

class FakeClient:
    def __init__(self, rows):
        self.rows, self.filters = rows, []

    def table(self, name):
        assert name == "documents"
        return self

    def select(self, *columns):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def test_upload_helper_compares_with_the_rest_of_the_fascicolo_only():
    rows = [row("1", "13/05/2025"),
            {**row("2", "01/01/2020"), "processing_status": "failed"},   # failed analyses are ignored
            row("3", "02/09/2025")]                                       # the new document itself
    client = FakeClient(rows)
    result = routes._fascicolo_review(client, 7, {"id": 3}, payload("02/09/2025"), "visura.pdf", "a" * 64)
    assert client.filters == [("fascicolo_id", "7")]
    assert result["compared_with"] == 1
    assert result["items"][0]["action"] == "new_version"


def test_upload_helper_never_raises():
    class Broken:
        def table(self, name):
            raise RuntimeError("database unavailable")

    assert routes._fascicolo_review(Broken(), 7, {"id": 3}, payload("02/09/2025"), "v.pdf", "a" * 64) is None


@pytest.mark.parametrize("odd", [{}, {"extracted_fields": "not a dict"}, {"document_type": None}])
def test_upload_helper_tolerates_odd_payloads(odd):
    result = routes._fascicolo_review(FakeClient([row("1", "13/05/2025")]), 7, {"id": 3}, odd, "v.pdf", "a" * 64)
    assert result is None or result["items"][0]["automatic_merge_allowed"] is False
