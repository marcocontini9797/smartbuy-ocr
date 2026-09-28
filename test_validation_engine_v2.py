"""Adversarial, entirely synthetic cases; no keys or external services needed."""
from copy import deepcopy
from datetime import date
import json

import pytest

from document_engine.cross_validation import cross_validate, norm_categoria, norm_energy_class, parse_quota, summarize
from document_engine.checklist import build_checklist
from document_engine.agent_review import build_agent_review
from document_engine.validation_rules import VERSION

TODAY = date(2026, 9, 28)
PROPERTY = {"id": 91, "typology": "appartamento", "contract": "vendita"}


def unit(category="A/2", sub="1", comune="Bologna", **extras):
    return {"comune": comune, "foglio": "10", "particella": "20", "subalterno": sub, "categoria": category, **extras}


def doc(did=1, refs=None, kind="visura_catastale", fields=None, **extras):
    return {"id": did, "document_type": kind, "file_name": f"synthetic-{did}.pdf", "extraction_confidence": .95,
            "extracted_fields": {"riferimenti_catastali": refs if refs is not None else [unit()], **(fields or {})}, **extras}


def run(documents, prop=None, **kwargs):
    return cross_validate(91, documents=documents, property_record=PROPERTY if prop is None else prop, today=TODAY, **kwargs)


def rules(findings, rule):
    return [f for f in findings if f.rule_id == rule]


@pytest.mark.parametrize("contract", ["vendita", "affitto"])
@pytest.mark.parametrize("category", ["C/2", "C/6", "C/7"])
def test_possible_accessory_alone_is_never_silently_accepted(contract, category):
    findings = run([doc(refs=[unit(category)])], {**PROPERTY, "contract": contract})
    issue = rules(findings, "category_use")[0]
    assert issue.status == "attention" and issue.severity == "high"
    assert "pertinenza" in issue.detail and issue.sources == ["doc:1"]


@pytest.mark.parametrize("category", ["C/2", "C/6", "C/1", "A/10", "D/1"])
def test_explicit_main_unit_has_a_real_category_conflict(category):
    issue = rules(run([doc(refs=[unit(category, ruolo_unita="principale")])]), "category_use")[0]
    assert issue.status == "conflict"
    assert issue.scope["subalterno"] == "1"
    assert issue.values[0]["source_path"] == "riferimenti_catastali[0].categoria"


def test_property_target_c2_cannot_hide_behind_another_apartment():
    docs = [doc(refs=[unit("C/2", "1"), unit("A/2", "2")])]
    issue = rules(run(docs, {**PROPERTY, "city": "Bologna", "foglio": "10", "particella": "20", "subalterno": "1"}), "category_use")[0]
    assert issue.status == "conflict"


@pytest.mark.parametrize("separate", [True, False])
def test_real_accessory_plus_identified_apartment_does_not_raise_use_problem(separate):
    docs = [doc(refs=[unit()]), doc(2, [unit("C/2", "2")])] if separate else [doc(refs=[unit(), unit("C/2", "2")])]
    assert rules(run(docs), "category_use") == []


@pytest.mark.parametrize("typology,category", [("magazzino", "C/2"), ("ufficio", "A/10"), ("box", "C/6"),
                                               ("negozio", "C/1"), ("laboratorio", "C/3"), ("capannone", "D/7"), ("appartamento", "A/11")])
def test_supported_non_residential_and_residential_categories(typology, category):
    assert not rules(run([doc(refs=[unit(category)])], {**PROPERTY, "typology": typology}), "category_use")


def test_multiunit_comparison_detects_category_change_on_the_correct_subalterno():
    docs = [doc(refs=[unit(), unit("C/6", "2")]), doc(2, [unit("C/2"), unit("C/6", "2")])]
    conflicts = [f for f in run(docs) if f.field == "catasto.categoria" and f.status == "conflict"]
    assert len(conflicts) == 1
    assert conflicts[0].scope["subalterno"] == "1"
    assert conflicts[0].sources == ["doc:1", "doc:2"]
    assert not any(f.status == "extraction_unstable" for f in run(docs))


def test_same_numbers_in_different_municipalities_do_not_confirm_each_other():
    docs = [doc(refs=[unit("A/2", comune="Bologna")]), doc(2, [unit("C/2", comune="Modena")])]
    assert not any(f.status == "consistent" for f in run(docs))
    assert rules(run(docs), "unit_scope")
    assert rules(run(docs), "category_use")


def test_order_of_units_and_documents_is_irrelevant():
    docs = [doc(refs=[unit(), unit("C/6", "2")]), doc(2, [unit("C/2"), unit("C/6", "2")])]
    a = [f.model_dump(mode="json") for f in run(docs)]
    docs.reverse()
    # Array paths change when units move, but finding identities and statuses must not.
    for d in docs:
        d["extracted_fields"]["riferimenti_catastali"].reverse()
    b = [f.model_dump(mode="json") for f in run(docs)]
    assert [(f["finding_id"], f["status"]) for f in a] == [(f["finding_id"], f["status"]) for f in b]


@pytest.mark.parametrize("mode", ["sandbox", "simulated", "test", "demo"])
def test_simulated_data_cannot_validate_real_property(mode):
    findings = run([doc(environment=mode), doc(2)])
    assert rules(findings, "source_eligibility")
    assert not any(f.status == "consistent" for f in findings)


@pytest.mark.parametrize("status", ["failed", "rejected", "queued", "processing"])
def test_failed_or_unfinished_readings_are_excluded(status):
    findings = run([doc(processing_status=status), doc(2)])
    assert not any(f.status == "consistent" for f in findings)
    assert rules(findings, "source_eligibility")


def test_foreign_property_sources_and_facts_cannot_leak_into_findings():
    findings = run([doc(property_id=800), doc(2)], facts=[{"source_document_id": 1, "fact_name": "energy_class", "fact_value": {"value": "G"}}])
    assert all("doc:1" not in f.sources for f in findings if f.rule_id != "source_eligibility")


def test_document_ids_are_required_instead_of_merging_doc_none():
    findings = run([doc(None), doc(None, fields={"classe_energetica": "G"})])
    assert len(rules(findings, "source_eligibility")) == 2
    assert not any(f.status == "consistent" for f in findings)


def test_copies_with_same_hash_are_one_independent_source():
    findings = run([doc(content_sha256="a" * 64), doc(2, content_sha256="a" * 64)])
    assert not any(f.status == "consistent" for f in findings)
    assert any(f.sources == ["doc:1", "doc:2"] for f in findings)


def test_low_confidence_c2_is_a_reading_to_confirm_not_a_certain_conflict():
    issue = rules(run([doc(refs=[unit("C/2", ruolo_unita="principale")], extraction_confidence=.1)]), "category_use")[0]
    assert issue.status == "attention" and "lettura" in issue.detail


def test_feedback_corrects_category_in_both_checklist_and_cross_validation():
    docs = [doc(refs=[unit("C/2", ruolo_unita="principale")])]
    facts = [{"id": "f", "source_document_id": 1, "fact_name": "riferimenti_catastali", "fact_value": {"value": [unit("C/2")]},
              "verification_status": "corrected", "verified_value": {"value": [unit()]}, "evidence_ids": ["e1"]}]
    findings = run(docs, facts=facts)
    assert not rules(findings, "category_use")
    checklist = build_checklist(property_record=PROPERTY, documents=docs, facts=facts, findings=findings)
    assert not any(i["category"] == "categoria_catastale" for row in checklist["items"] for i in row["issues"])


def test_rejected_alias_cannot_be_resurrected_by_document():
    docs = [doc(refs=[], fields={"categoria": "C/2"})]
    facts = [{"source_document_id": 1, "fact_name": "category", "fact_value": {"value": "C/2"}, "verification_status": "rejected"}]
    assert not rules(run(docs, facts=facts), "category_use")


def test_effective_facts_preserve_evidence_and_provenance():
    facts = [{"id": "f", "source_document_id": 1, "fact_name": "riferimento", "fact_value": {"value": unit("C/2", ruolo_unita="principale")},
              "confidence_score": .9, "evidence_ids": ["e1"], "provenance": {"source_page": 2, "source_text": "C/2 deposito"}}]
    issue = rules(run([], facts=facts), "category_use")[0]
    assert issue.evidence_ids == ["e1"]
    assert issue.values[0]["page"] == 2 and issue.values[0]["fact_id"] == "f"
    json.dumps(issue.model_dump(mode="json"), allow_nan=False)


@pytest.mark.parametrize("raw", ["C", "C/99", "A/12", "non disponibile"])
def test_invalid_category_is_a_missing_reading_not_a_clean_result(raw):
    assert norm_categoria(raw) is None
    assert any(f.field == "catasto.categoria_formato" for f in run([doc(refs=[unit(raw)])]))


@pytest.mark.parametrize("raw", ["non disponibile", "da verificare", "non classificato", "A/2", "C2"])
def test_energy_class_never_comes_from_letters_inside_prose(raw):
    assert norm_energy_class(raw) is None
    findings = run([doc(kind="ape", fields={"classe_energetica": raw})])
    assert any(f.field == "ape.classe_formato" for f in findings)


def test_energy_c_is_independent_from_cadastral_c2():
    findings = run([doc(kind="ape", fields={"classe_energetica": "C"})])
    assert not rules(findings, "category_use")
    assert not any(f.field == "ape.classe_formato" for f in findings)


@pytest.mark.parametrize("quota,expected", [("piena proprietà per 1/2", .5), ("1/10", .1), ("25%", .25), ("1/0", None)])
def test_quota_honors_explicit_fraction_before_full_ownership_words(quota, expected):
    assert parse_quota(quota) == expected


@pytest.mark.parametrize("fields,field", [
    ({"data_emissione": "2026-09-01", "data_scadenza": "2026-08-01"}, "documento.cronologia.data_scadenza"),
    ({"data_inizio": "2026-09-01", "data_fine": "2025-08-01"}, "documento.cronologia.data_fine"),
    ({"data_visura": "2026-02-30"}, "documento.data_formato.data_visura"),
    ({"data_emissione": "2027-01-01"}, "documento.data_futura.data_emissione"),
    ({"prezzo_eur": 100000, "caparra_eur": 120000}, "economia.caparra_eur"),
    ({"canone_annuo_eur": 12000, "canone_mensile_eur": 800}, "economia.canone_mensile_eur"),
    ({"superficie_utile_mq": -80}, "superficie_utile_mq.formato"),
    ({"prezzo_eur": "non leggibile"}, "prezzo_eur.formato"),
    ({"diritti_e_quote": "3/2"}, "quota_proprieta.formato"),
])
def test_internal_document_inconsistencies(fields, field):
    findings = run([doc(fields=fields)])
    assert any(f.field == field for f in findings)


def test_correct_dates_and_amounts_do_not_raise_internal_alerts():
    fields = {"data_emissione": "2025-01-01", "data_scadenza": "2035-01-01", "prezzo_eur": 100000,
              "caparra_eur": 10000, "canone_annuo_eur": 12000, "canone_mensile_eur": 1000}
    findings = run([doc(fields=fields)])
    assert not any(f.rule_id in {"date_order", "amount_relation", "field_format"} for f in findings)


def test_historical_differences_remain_open_without_picking_newest_as_truth():
    docs = [doc(fields={"data_visura": "2020-01-01"}), doc(2, [unit("C/2")], fields={"data_visura": "2026-09-01"})]
    finding = next(f for f in run(docs) if f.field == "catasto.categoria")
    assert finding.status == "attention" and finding.canonical_value is None
    assert "date diverse" in finding.detail


@pytest.mark.parametrize("fields", [{"conformita_urbanistica": False}, {"destinazione_uso": {"valore": "deposito", "fonte": "uso deposito", "confidence": .9}}])
def test_technical_and_usage_evidence_produces_actionable_agent_review(fields):
    docs = [doc(kind="relazione_tecnica_integrata", fields=fields)]
    findings = run(docs)
    review = build_agent_review(91, PROPERTY, docs, findings)
    assert review["actions"]
    assert review["actions"][0]["sources"] == ["doc:1"]
    assert review["actions"][0]["finding_ids"]
    assert "tecnico" in review["actions"][0]["next_step"].lower()


def test_checklist_c2_does_not_go_green_and_links_one_finding_only():
    docs = [doc(refs=[unit("C/2")])]
    findings = run(docs)
    checklist = build_checklist(property_record=PROPERTY, documents=docs, findings=findings)
    visura = next(i for i in checklist["items"] if i["key"] == "visura_catastale")
    issues = [i for i in visura["issues"] if i.get("rule_id") == "category_use"]
    assert visura["status"] == "to_check" and len(issues) == 1
    assert issues[0]["finding_id"] in {f.finding_id for f in findings}


def test_inputs_are_not_mutated_and_output_is_json_serializable():
    docs = [doc(refs=[unit("C/2", ruolo_unita="principale")])]
    original = deepcopy(docs)
    findings = run(docs)
    assert docs == original
    payload = json.dumps([f.model_dump(mode="json") for f in findings], allow_nan=False)
    assert "category_use" in payload
    assert summarize(findings)["engine_version"] == VERSION


def test_attention_cannot_leave_summary_at_100_percent_verified():
    findings = run([doc(refs=[unit("C/2")]), doc(2, [unit("C/2")])])
    assert summarize(findings)["verified_ratio"] < 1


def test_derived_fields_in_an_official_pdf_are_not_independent_confirmation():
    docs = [doc(content_sha256="a" * 64), doc(2, content_sha256="b" * 64, fields={"_validation_origin": {"document_id": 1}})]
    assert not any(f.status == "consistent" for f in run(docs))


def test_multiunit_derived_fields_are_not_independent_either():
    refs = [unit(), unit("C/6", "2")]
    docs = [doc(refs=refs, content_sha256="a" * 64),
            doc(2, refs=refs, content_sha256="b" * 64, fields={"_validation_origin": {"document_id": 1}})]
    assert not any(f.status == "consistent" for f in run(docs))


def test_completed_but_empty_document_is_not_marked_verified():
    document = {"id": 1, "document_type": "visura_catastale", "processing_status": "completed", "extracted_fields": {}}
    findings = run([document])
    assert rules(findings, "source_eligibility")
    checklist = build_checklist(property_record=PROPERTY, documents=[document], findings=findings)
    assert next(i for i in checklist["items"] if i["key"] == "visura_catastale")["status"] != "verified"


def test_low_confidence_surface_cannot_create_a_positive_ratio():
    findings = run([doc(fields={"superficie_utile_mq": {"valore": 80, "confidence": .1}, "superficie_commerciale_mq": 100})])
    assert next(f for f in findings if f.field == "superficie.rapporto").status == "attention"


def test_technical_declarations_are_compared_across_documents():
    docs = [doc(kind="relazione_tecnica_integrata", fields={"conformita_urbanistica": True}),
            doc(2, kind="relazione_tecnica_integrata", fields={"conformita_urbanistica": False})]
    findings = run(docs)
    assert any(f.field == "tecnica.conformita_urbanistica" and f.status == "conflict" for f in findings)


def test_civic_suffixes_are_not_lost():
    from document_engine.cross_validation import norm_address
    assert norm_address("Via Roma 12/A") != norm_address("Via Roma 12/B")
    assert norm_address("Via Roma 12/A") == norm_address("Via Roma 12a")


def test_one_surname_cannot_confirm_two_distinct_people():
    docs = [doc(fields={"intestatari": ["Rossi"]}), doc(2, fields={"intestatari": ["Rossi Mario", "Rossi Anna"]})]
    assert not any(f.field == "proprietari" and f.status in {"consistent", "compatible"} for f in run(docs))


def test_second_reading_checks_every_unit_not_only_the_last_one():
    from document_engine.cross_validation import extraction_disagreements
    first = {"riferimenti_catastali": [unit(), unit("C/6", "2")]}
    second = {"riferimenti_catastali": [unit("C/2"), unit("C/6", "2")]}
    assert extraction_disagreements(first, second)
    assert extraction_disagreements(first, {"riferimenti_catastali": list(reversed(first["riferimenti_catastali"]))}) == {}


def test_second_reading_checks_dates_and_technical_booleans():
    from document_engine.cross_validation import extraction_disagreements
    assert extraction_disagreements({"data_scadenza": "2030-01-01"}, {"data_scadenza": "2031-01-01"})
    assert extraction_disagreements({"data_scadenza": "2030-01-01"}, {"data_scadenza": "01/01/2030"}) == {}
    assert extraction_disagreements({"conformita_catastale": True}, {"conformita_catastale": False})


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_are_reviewable_and_serialize(number):
    findings = run([doc(fields={"superficie_utile_mq": number})])
    assert any(f.field == "superficie_utile_mq.formato" for f in findings)
    json.dumps([f.model_dump(mode="json") for f in findings], allow_nan=False)


def test_correcting_a_single_category_keeps_unit_identity_and_role():
    docs = [doc()]
    facts = [{"id": "f", "source_document_id": 1, "fact_name": "category", "fact_value": {"value": "A/2"},
              "verification_status": "corrected", "verified_value": {"value": "C/2"}, "evidence_ids": ["e1"]}]
    prop = {**PROPERTY, "city": "Bologna", "foglio": "10", "particella": "20", "subalterno": "1"}
    findings = run(docs, prop, facts=facts)
    issue = rules(findings, "category_use")[0]
    assert issue.status == "conflict" and issue.scope["subalterno"] == "1"
    assert issue.values[0]["fact_id"] == "f" and issue.evidence_ids == ["e1"]
    assert any(f.field == "catasto.foglio" for f in findings)


def test_verified_alias_overrides_an_older_fact_with_another_name():
    facts = [{"id": "old", "source_document_id": 1, "fact_name": "energy_class", "fact_value": {"value": "B"}},
             {"id": "confirmed", "source_document_id": 1, "fact_name": "classe_energetica", "fact_value": {"value": "C"}, "verification_status": "verified"}]
    findings = run([], facts=facts)
    energy = [f for f in findings if f.field == "classe_energetica"]
    assert len(energy) == 1 and energy[0].canonical_value == "C"
    assert energy[0].status == "insufficient_evidence"


def test_historical_main_unit_category_requires_reconstructing_change():
    docs = [doc(refs=[unit("C/2", ruolo_unita="principale")], fields={"data_visura": "2010-01-01"}),
            doc(2, fields={"data_visura": "2026-09-01"})]
    issue = rules(run(docs), "category_use")[0]
    assert issue.status == "attention" and "variazione" in issue.detail


def test_unspecified_class_field_is_not_assumed_to_be_energy_class():
    assert not any(f.field == "classe_energetica" for f in run([doc(fields={"classe": "C"})]))
