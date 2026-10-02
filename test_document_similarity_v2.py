"""Offline adversarial tests for document similarity and conservative lineage."""
from copy import deepcopy
from datetime import date
import hashlib
import pytest
from document_engine.document_similarity import (
    MAX_TEXT_CHARS, calculate_file_hash,calculate_text_similarity,
    compare_metadata,compare_documents,
)

TODAY=date(2026,9,30)
TEXT=("La presente visura descrive l immobile censito nel comune con identificativi "
      "catastali e dati relativi alla consistenza alla categoria alla rendita e "
      "agli intestatari risultanti dagli atti disponibili alla data della richiesta.")

def unit(sub="3",category="A/2",comune="Bologna",**extra):
    return {"comune":comune,"foglio":"12","particella":"34","subalterno":sub,"categoria":category,**extra}

def doc(**extra):
    return {"document_type":"visura_catastale","ocr_text":TEXT,
            "extracted_fields":{"riferimenti_catastali":[unit()]},**extra}

def pair(a,b):
    return compare_documents(a,b,today=TODAY)

def test_sha256_compatible_with_standard():
    assert calculate_file_hash(b"sample")==hashlib.sha256(b"sample").hexdigest()

@pytest.mark.parametrize("content",["sample",None,42])
def test_hash_requires_bytes(content):
    with pytest.raises(TypeError): calculate_file_hash(content)

@pytest.mark.parametrize("key",["sha256","content_sha256","checksum_sha256","file_sha256"])
def test_hash_aliases_identify_duplicate(key):
    h=calculate_file_hash(b"document")
    result=pair({key:h.upper()},{"content_sha256":h})
    assert result["status"]=="duplicate"
    assert result["similarity_score"]==1
    assert result["duplicate_exact"] is True
    assert result["automatic_merge_allowed"] is False

@pytest.mark.parametrize("value",["abc",True,12,"",None,hashlib.sha256(b"").hexdigest()])
def test_invalid_empty_or_missing_hash_never_duplicate(value):
    assert not pair({"sha256":value},{"sha256":value})["duplicate_exact"]

def test_inconsistent_hash_aliases_cannot_mask_different_content():
    a={"sha256":"a"*64,"content_sha256":"b"*64}
    assert not pair(a,{"sha256":"a"*64})["duplicate_exact"]

def test_identical_ocr_can_be_similar_without_hash():
    result=pair(doc(),doc())
    assert result["status"]=="similar"
    assert result["similarity_score"]>=.8

def test_different_hashes_can_still_be_similar_scans():
    result=pair(doc(sha256="a"*64),doc(sha256="b"*64))
    assert result["status"]=="similar"
    assert not result["duplicate_exact"]

@pytest.mark.parametrize("a,b",[({},{}),({"document_type":"ape"},{"document_type":"ape"}),
                                ({"ocr_text":"APE classe C"},{"ocr_text":"APE classe C"})])
def test_absence_or_short_content_is_not_evidence(a,b):
    assert pair(a,b)["status"]=="insufficient_evidence"

def test_none_document_type_is_not_a_match():
    assert pair({}, {})["scores"]["type"]==0

def test_metadata_equal_does_not_prove_updated_document():
    result=pair(doc(metadata={"foo":"bar"}),doc(metadata={"foo":"bar"}))
    assert result["status"]!="same_document_updated"

def test_missing_values_and_technical_metadata_are_excluded():
    assert compare_metadata({"owner":None,"created_at":"today"},{"owner":None,"created_at":"today"})==0
    assert compare_metadata({"confidence":.9,"organization":{"name":"x"}},{"confidence":.9,"organization":{"name":"x"}})==0

def test_metadata_union_penalises_low_overlap():
    assert compare_metadata({"a":1,"b":2,"c":3},{"a":1})==pytest.approx(1/3,abs=.001)
    assert compare_metadata({"a":1},{"a":1,"b":2,"c":3})==pytest.approx(1/3,abs=.001)

def test_false_and_zero_are_not_missing_but_are_different_types():
    assert compare_metadata({"x":False},{"x":False})==1
    assert compare_metadata({"x":False},{"x":0})==0

def test_structured_wrappers_ignore_citation_and_key_order():
    a={"owners":{"valore":["Mario","Luigi"],"fonte":"page1","confidence":.9}}
    b={"owners":{"value":["Luigi","Mario"],"source_text":"page2","confidence":.3}}
    assert compare_metadata(a,b)==1

@pytest.mark.parametrize("a,b",[(TEXT,TEXT.upper()),(TEXT,TEXT.replace(" ","\n")),
                               ("docu-\nmento catastale","documento catastale")])
def test_text_normalisation(a,b):
    assert calculate_text_similarity(a,b)==1

def test_similarity_is_symmetric():
    a=TEXT+" prezzo 150000"
    b=TEXT.replace("catastali","catastale")+" importo 155000"
    assert calculate_text_similarity(a,b)==calculate_text_similarity(b,a)
    assert pair(doc(ocr_text=a),doc(ocr_text=b))["similarity_score"]==pair(doc(ocr_text=b),doc(ocr_text=a))["similarity_score"]

def test_long_text_never_compares_only_shared_prefix():
    a="a"*MAX_TEXT_CHARS+"1"
    b="a"*MAX_TEXT_CHARS+"2"
    result=pair(doc(ocr_text=a),doc(ocr_text=b))
    assert result["comparison_limited"] and result["status"]=="insufficient_evidence"
    assert calculate_text_similarity(a,b)==0

def test_deep_structures_fail_closed():
    tree={"value":1}
    for _ in range(20): tree={"nested":tree}
    result=pair(doc(metadata=tree),doc(metadata=tree))
    assert result["comparison_limited"]
    assert result["status"]=="insufficient_evidence"

def test_numbers_changed_in_similar_boilerplate_are_flagged():
    result=pair(doc(ocr_text=TEXT+" prezzo 150000"),doc(ocr_text=TEXT+" prezzo 155000"))
    assert result["status"]=="possible_conflict"
    assert any(c["kind"]=="numeric_change_requires_reading" for c in result["conflicts"])

def test_wrong_property_blocks_even_matching_hash():
    result=pair(doc(property_id=1,sha256="a"*64),doc(property_id=2,sha256="a"*64))
    assert result["status"]=="out_of_scope" and not result["duplicate_exact"]

def test_account_boundary_is_respected():
    assert pair(doc(user_id="A"),doc(agente_id="B"))["status"]=="out_of_scope"

def test_inconsistent_property_aliases_are_not_silently_merged():
    result=pair(doc(property_id=1,fascicolo_id="2"),doc(property_id=1))
    assert result["status"]=="insufficient_evidence"
    assert result["reasons"]==["inconsistent"]

def test_different_subalterni_are_different_documents_despite_boilerplate():
    result=pair(doc(),doc(extracted_fields={"riferimenti_catastali":[unit("4")]}))
    assert result["status"]=="different"
    assert result["identity"]["relation"]=="different_units"

def test_municipal_names_and_codes_are_not_guessed_equivalent_or_different():
    other=unit()
    other["codice_comune"]="A944"
    result=pair(doc(),doc(extracted_fields={"riferimenti_catastali":[other]}))
    assert result["identity"]["relation"]=="unknown"

def test_missing_section_does_not_prove_a_different_unit():
    result=pair(doc(),doc(extracted_fields={"riferimenti_catastali":[unit(sezione="A")]}))
    assert result["identity"]["relation"]=="incomplete"

def test_same_numbers_in_different_municipalities_are_not_same_unit():
    result=pair(doc(),doc(extracted_fields={"riferimenti_catastali":[unit(comune="Modena")]}))
    assert result["identity"]["relation"]=="different_units"

def test_c2_versus_a2_on_same_unit_is_flagged():
    result=pair(doc(),doc(extracted_fields={"riferimenti_catastali":[unit(category="C/2")]}))
    assert result["status"]=="possible_conflict"
    assert any(c["kind"]=="same_unit_category_disagreement" for c in result["conflicts"])

def test_apartment_and_garage_not_compared_as_one_unit():
    a=doc(extracted_fields={"riferimenti_catastali":[unit(),unit("4","C/6")]})
    b=doc(extracted_fields={"riferimenti_catastali":[unit("4","C/6"),unit()]})
    result=pair(a,b)
    assert result["status"]=="similar" and not result["conflicts"]

def test_internal_category_ambiguity_never_hides():
    a=doc(extracted_fields={"riferimenti_catastali":[unit(),unit(category="C/2")]})
    result=pair(a,a)
    assert any(c["kind"]=="ambiguous_readings_within_one_document" for c in result["conflicts"])

def test_same_file_with_conflicting_classification_still_requires_review():
    result=pair(doc(sha256="a"*64),doc(sha256="a"*64,document_type="ape"))
    assert result["status"]=="duplicate" and result["requires_review"]

def test_numeric_formats_are_not_false_business_conflicts():
    result=pair(doc(extracted_fields={"superficie_utile_mq":{"valore":"80,5 mq"}}),
                doc(extracted_fields={"superficie_utile_mq":80.5}))
    assert not any(c["field"]=="superficie_utile" for c in result["conflicts"])

def test_surface_types_not_compared_to_each_other():
    result=pair(doc(extracted_fields={"superficie_utile_mq":80}),
                doc(extracted_fields={"superficie_commerciale_mq":100}))
    assert not result["conflicts"]

def test_distinct_owner_names_survive_high_text_similarity():
    result=pair(doc(extracted_fields={"intestatari":["Mario Rossi"]}),
                doc(extracted_fields={"intestatari":["Luca Bianchi"]}))
    assert result["status"]=="possible_conflict"

def test_owner_token_order_not_false_conflict():
    assert not pair(doc(extracted_fields={"intestatari":["Mario Rossi"]}),
                    doc(extracted_fields={"intestatari":["ROSSI MARIO"]}))["conflicts"]

def versioned():
    return (doc(document_series_id="private-series",document_date="2026-01-01"),
            doc(document_series_id="private-series",document_date="2026-06-01"))

def test_updated_candidate_requires_explicit_series_unit_type_and_chronology():
    a,b=versioned()
    result=pair(a,b)
    assert result["status"]=="same_document_updated"
    assert result["version"]=={"assessment":"candidate_requires_review","newer":"b"}
    assert result["requires_review"] and not result["automatic_merge_allowed"]
    assert pair(b,a)["version"]["newer"]=="a"

@pytest.mark.parametrize("change",[
    {"document_series_id":None},{"document_date":"2099-01-01"},
    {"document_date":"not-a-date"},{"document_date":"2026-01-01"},
    {"document_type":"ape"},{"extracted_fields":{"riferimenti_catastali":[unit("4")]}},
    {"extracted_fields":{}},{"document_date":None,"updated_at":"2026-09-30"},
])
def test_unproven_revision_not_marked_updated(change):
    a,b=versioned(); b.update(change)
    assert pair(a,b)["status"]!="same_document_updated"

def test_document_dates_in_conflicting_locations_block_revision():
    a,b=versioned()
    b["metadata"]={"issue_date":"2026-07-01"}
    assert pair(a,b)["status"]!="same_document_updated"

def test_no_input_mutation_or_personal_payloads_in_result():
    a=doc(extracted_fields={"intestatari":["Persona Segreta"]},file_name="secret.pdf",user_id="A")
    b=doc(extracted_fields={"intestatari":["Altro Nome"]},user_id="A")
    old=deepcopy([a,b]); result=pair(a,b)
    assert [a,b]==old
    assert all(x not in str(result) for x in ["Persona Segreta","Altro Nome","secret.pdf"])

def test_bad_api_input_is_explicit():
    with pytest.raises(TypeError): compare_documents([], {})

def test_sandbox_cannot_supply_duplicate_or_version_evidence_for_production():
    assert pair(doc(environment="sandbox",sha256="a"*64),
                doc(environment="production",sha256="a"*64))["status"]=="out_of_scope"

def test_total_structured_text_budget_is_bounded():
    fields={f"k{i}":"x"*100000 for i in range(3)}
    result=pair(doc(metadata=fields),doc(metadata=fields))
    assert result["comparison_limited"]
    assert result["status"]=="insufficient_evidence"

def test_oversized_multiunit_inputs_are_not_partially_compared():
    result=pair(doc(extracted_fields={"riferimenti_catastali":[unit(str(i)) for i in range(201)]}),doc())
    assert result["comparison_limited"]
    assert result["status"]=="insufficient_evidence"
