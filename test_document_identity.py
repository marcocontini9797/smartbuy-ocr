"""Offline tests for the identity adapter and resolver (no network, no cost)."""
from copy import deepcopy
from datetime import date

import pytest

from document_engine.document_identity import (
    VERDICTS,
    adapt_extracted_fields,
    parse_issue_date,
    resolve_document_identity,
)
from document_engine.document_similarity import calculate_file_hash, compare_documents
from document_engine.fascicolo_integration import build_fascicolo_comparisons

TODAY = date(2026, 9, 30)
TEXT = ("La presente visura descrive l immobile censito nel comune con identificativi "
        "catastali e dati relativi alla consistenza alla categoria alla rendita e "
        "agli intestatari risultanti dagli atti disponibili alla data della richiesta.")


def unit(particella="34", category="A/2", sub="3"):
    return {"comune": "Bologna", "foglio": "12", "particella": particella, "subalterno": sub, "categoria": category}


def visura(issued, *, particella="34", category="A/2", ocr_extra="", **top):
    """A visura as the extraction schema produces it, passed through the adapter."""
    fields = adapt_extracted_fields({"riferimento": unit(particella, category), "data_visura": issued})
    return {"document_type": "visura_catastale", "ocr_text": f"{TEXT} {ocr_extra}".strip(),
            "extracted_fields": fields, **top}


def resolve(a, b, **kwargs):
    similarity = compare_documents(a, b, today=TODAY)
    return similarity, resolve_document_identity(similarity, a, b, today=TODAY, **kwargs)


# --- parse_issue_date -------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("2025-05-13", date(2025, 5, 13)), ("13/05/2025", date(2025, 5, 13)),
    ("13-05-2025", date(2025, 5, 13)), ("13.05.2025", date(2025, 5, 13)),
    (" 3/5/2025 ", date(2025, 5, 3)),
])
def test_parse_issue_date_accepts_iso_and_day_first(raw, expected):
    assert parse_issue_date(raw) == expected


@pytest.mark.parametrize("raw", ["13/05/25", "31/02/2025", "13 maggio 2025", "2025", "", None, 20250513])
def test_parse_issue_date_refuses_ambiguous_or_invalid(raw):
    assert parse_issue_date(raw) is None


# --- adapter ----------------------------------------------------------------

def test_adapter_maps_riferimento_and_data_visura():
    fields = adapt_extracted_fields({"riferimento": unit(), "data_visura": "13/05/2025"})
    assert fields["riferimenti_catastali"] == [unit()]
    assert fields["document_date"] == "2025-05-13"


def test_adapter_never_modifies_input_or_invents_a_series():
    original = {"riferimento": unit(), "data_visura": "13/05/2025", "data_emissione": "13/05/2025"}
    snapshot = deepcopy(original)
    adapted = adapt_extracted_fields(original)
    assert original == snapshot
    assert "document_series_id" not in adapted
    assert adapted["data_emissione"] == "2025-05-13"


def test_adapter_keeps_existing_units_and_dates():
    existing = [unit("99")]
    fields = adapt_extracted_fields({"riferimento": unit(), "riferimenti_catastali": existing,
                                     "document_date": "2024-01-02", "data_visura": "13/05/2025"})
    assert fields["riferimenti_catastali"] == existing
    assert fields["document_date"] == "2024-01-02"


def test_adapter_skips_empty_reference():
    assert "riferimenti_catastali" not in adapt_extracted_fields({"riferimento": {"foglio": None, "comune": ""}})


@pytest.mark.parametrize("fields", [
    {"data_visura": "13/05/2025", "data_rilascio": "14/05/2025"},   # two different dates: not guessed
    {"data_visura": "13/05/2025", "data_rilascio": "boh"},          # one unreadable: not guessed
    {"data_visura": "13 maggio 2025"},
])
def test_adapter_sets_no_date_unless_unambiguous(fields):
    assert "document_date" not in adapt_extracted_fields(fields)


def test_adapter_unwraps_value_wrappers():
    fields = adapt_extracted_fields({"data_visura": {"valore": "13/05/2025", "confidence": .9}})
    assert fields["document_date"] == "2025-05-13"


# --- the two cases from the design discussion ------------------------------------

def test_case_a_updated_visura_is_a_newer_candidate_not_a_conflict_on_the_date():
    old = visura("13/05/2025", ocr_extra="Data richiesta 13/05/2025")
    new = visura("02/09/2025", ocr_extra="Data richiesta 02/09/2025")
    similarity, resolution = resolve(old, new)
    assert similarity["status"] == "possible_conflict"      # the engine alone is (rightly) cautious
    assert resolution["verdict"] == "newer_version_candidate"
    assert resolution["newer"] == "b"
    assert resolution["lineage"] == "inferred_from_unit_type_and_date"
    assert "numeric_changes_match_issue_dates" in resolution["explained"]
    assert resolution["open_conflicts"] == []
    assert resolution["requires_review"] and not resolution["automatic_merge_allowed"]


def test_case_a_with_explicit_series_reports_explicit_lineage():
    old = visura("13/05/2025", ocr_extra="Data richiesta 13/05/2025", document_series_id="S-1")
    new = visura("02/09/2025", ocr_extra="Data richiesta 02/09/2025", document_series_id="S-1")
    _, resolution = resolve(old, new)
    assert resolution["verdict"] == "newer_version_candidate"
    assert resolution["lineage"] == "explicit_series"


def test_newer_is_a_when_the_document_on_file_is_the_later_one():
    old = visura("02/09/2025", ocr_extra="Data richiesta 02/09/2025")
    new = visura("13/05/2025", ocr_extra="Data richiesta 13/05/2025")
    _, resolution = resolve(old, new)
    assert resolution["newer"] == "a"


def test_changed_surface_is_not_explained_away_by_a_date_change():
    old = visura("13/05/2025", ocr_extra="Data 13/05/2025 superficie 75")
    new = visura("02/09/2025", ocr_extra="Data 02/09/2025 superficie 80")
    _, resolution = resolve(old, new)
    assert resolution["verdict"] == "newer_version_candidate"
    assert resolution["explained"] == []
    assert "ocr_numeric_tokens" in resolution["open_conflicts"]


def test_structured_changes_stay_visible_on_a_newer_candidate():
    old = visura("13/05/2025", category="A/2")
    new = visura("02/09/2025", category="A/3")
    _, resolution = resolve(old, new)
    assert resolution["verdict"] == "newer_version_candidate"
    assert "categoria" in resolution["open_conflicts"]


def test_case_b_different_parcel_without_expected_unit_is_not_decided():
    old, new = visura("13/05/2025", particella="20"), visura("02/09/2025", particella="99")
    similarity, resolution = resolve(old, new)
    assert similarity["status"] == "different"
    assert resolution["verdict"] == "different_units_expectation_unknown"


def test_case_b_with_expected_unit_flags_the_document_outside_it():
    old, new = visura("13/05/2025", particella="20"), visura("02/09/2025", particella="99")
    _, resolution = resolve(old, new, expected_units=[unit("20")])
    assert resolution["verdict"] == "unit_outside_expected"
    assert resolution["expected_unit"] == {"a": "matches", "b": "other"}
    assert resolution["requires_review"]


def test_neither_document_matching_the_expected_unit():
    old, new = visura("13/05/2025", particella="20"), visura("02/09/2025", particella="99")
    _, resolution = resolve(old, new, expected_units=[unit("55")])
    assert resolution["verdict"] == "neither_matches_expected"


def test_garage_next_to_the_expected_apartment_is_only_an_accessory_candidate():
    apartment = visura("13/05/2025", particella="20", category="A/2")
    garage = visura("02/09/2025", particella="20", category="C/6")
    garage["extracted_fields"]["riferimenti_catastali"][0]["subalterno"] = "9"
    _, resolution = resolve(apartment, garage, expected_units=[unit("20")])
    assert resolution["verdict"] == "ancillary_unit_candidate"
    assert "accessory_category_not_proof_of_same_building" in resolution["reasons"]
    assert resolution["requires_review"]


def test_expected_unit_that_is_itself_incomplete_is_not_used():
    old, new = visura("13/05/2025", particella="20"), visura("02/09/2025", particella="99")
    _, resolution = resolve(old, new, expected_units=[{"comune": "Bologna", "foglio": "12"}])
    assert resolution["verdict"] == "different_units_expectation_unknown"
    assert "expected_unit_incomplete" in resolution["reasons"]


# --- other verdicts -------------------------------------------------------------------

def test_exact_duplicate_passes_through():
    digest = calculate_file_hash(b"same file")
    a = visura("13/05/2025", sha256=digest)
    b = visura("13/05/2025", sha256=digest)
    _, resolution = resolve(a, b)
    assert resolution["verdict"] == "exact_duplicate"


def test_same_unit_different_document_types_is_informational():
    visura_doc = visura("13/05/2025")
    plan = {"document_type": "planimetria_catastale", "ocr_text": TEXT,
            "extracted_fields": adapt_extracted_fields({"riferimento": unit()})}
    _, resolution = resolve(visura_doc, plan)
    assert resolution["verdict"] == "same_unit_different_document_types"
    assert resolution["requires_review"] is False


def test_future_issue_date_is_never_a_newer_version():
    old, new = visura("13/05/2025"), visura("02/09/2027")
    _, resolution = resolve(old, new)
    assert resolution["verdict"] == "same_unit_unresolved"
    assert "future_issue_date" in resolution["reasons"]


def test_same_date_with_a_structured_difference_is_a_conflict():
    old, new = visura("13/05/2025", category="A/2"), visura("13/05/2025", category="A/3")
    _, resolution = resolve(old, new)
    assert resolution["verdict"] == "same_unit_conflict"


def test_units_missing_leaves_identity_unresolved_with_reasons():
    a = {"document_type": "visura_catastale", "ocr_text": TEXT, "extracted_fields": {}}
    b = visura("13/05/2025")
    _, resolution = resolve(a, b)
    assert resolution["verdict"] == "identity_unresolved"
    assert "document_a_units_missing" in resolution["reasons"]


def test_out_of_scope_is_passed_through():
    a, b = visura("13/05/2025", property_id=1), visura("13/05/2025", property_id=2)
    _, resolution = resolve(a, b)
    assert resolution["verdict"] == "out_of_scope"


def test_every_verdict_is_known_and_merge_is_never_allowed():
    seen = []
    cases = [
        (visura("13/05/2025"), visura("02/09/2025")),
        (visura("13/05/2025", particella="20"), visura("13/05/2025", particella="99")),
        (visura("13/05/2025", property_id=1), visura("13/05/2025", property_id=2)),
        ({"document_type": "visura_catastale", "ocr_text": TEXT}, visura("13/05/2025")),
    ]
    for a, b in cases:
        _, resolution = resolve(a, b)
        seen.append(resolution["verdict"])
        assert resolution["verdict"] in VERDICTS
        assert resolution["automatic_merge_allowed"] is False
    assert len(set(seen)) > 1


def test_resolver_does_not_mutate_its_inputs():
    a, b = visura("13/05/2025", ocr_extra="Data 13/05/2025"), visura("02/09/2025", ocr_extra="Data 02/09/2025")
    similarity = compare_documents(a, b, today=TODAY)
    snapshot = deepcopy((a, b, similarity))
    resolve_document_identity(similarity, a, b, today=TODAY, expected_units=[unit()])
    assert (a, b, similarity) == snapshot


# --- integration layer -------------------------------------------------------------------

def test_integration_adds_the_resolution_from_raw_extraction_fields():
    payload = {"document_type": "visura_catastale", "ocr_text": f"{TEXT} Data richiesta 02/09/2025",
               "extracted_fields": {"riferimento": unit(), "data_visura": "02/09/2025"}}
    existing = [{"id": "doc-1", "document_type": "visura_catastale",
                 "ocr_text": f"{TEXT} Data richiesta 13/05/2025",
                 "extracted_fields": {"riferimento": unit(), "data_visura": "13/05/2025"}}]
    comparisons = build_fascicolo_comparisons(
        payload, new_document_id="doc-2", filename="visura.pdf", sha256=calculate_file_hash(b"new"),
        existing_documents=existing, expected_units=[unit()])
    resolution = comparisons[0]["identity_resolution"]
    assert resolution["verdict"] == "newer_version_candidate"
    assert resolution["newer"] == "b"
    assert resolution["automatic_merge_allowed"] is False
