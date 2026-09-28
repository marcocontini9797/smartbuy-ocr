"""Synthetic dossiers: operation identity, evidence discipline and review order."""
from copy import deepcopy
import json

import pytest

from core.operational_models import CrossValidationFinding
from document_engine.agent_review import build_agent_review
from document_engine.agent_investigation import build_investigation_plan
from document_engine.cross_validation import extraction_disagreements
from document_engine.validation_coverage import build_validation_coverage
from test_validation_engine_v2 import TODAY, PROPERTY, doc, unit, run, rules


def link(**extra):
    return {"riferimento": "Bologna registro preliminari RP/2026/123", "data": "2026-08-01",
            "stato_documento": "sottoscritto", "fonte": "Richiamato il preliminare RP/2026/123 del 1 agosto 2026", "confidence": .98, **extra}


def condition(state, **extra):
    return {"identificativo": "art. 4", "descrizione": "Ottenimento finanziamento", "stato": state,
            "fonte": "La condizione di cui all’art. 4 risulta " + state, "confidence": .95, **extra}


def dossier():
    return [doc(1, kind="preliminare_compravendita", fields={"collegamento_operazione": link(), "data": "2026-08-01",
            "promittente_venditore": ["Mario Rossi"], "promittente_acquirente": ["Anna Verdi"], "prezzo_eur": 100000,
            "condizioni_dettaglio": [condition("pendente")]}),
            doc(2, kind="atto_compravendita", fields={"collegamento_operazione": link(), "data_atto": "2026-09-20",
            "parte_venditrice": ["Rossi Mario"], "parte_acquirente": ["Verdi Anna"], "prezzo_eur": 100000,
            "condizioni_dettaglio": [condition("avverata")]})]


def comparisons(docs):
    return rules(run(docs), "operation_comparison")


def test_linked_signed_contracts_compare_same_roles_and_price():
    rows = comparisons(dossier())
    assert {f.field for f in rows} == {"operazione.venditori", "operazione.acquirenti", "operazione.prezzo"}
    assert all(f.status == "consistent" and f.scope["operation_date"] == "2026-08-01" for f in rows)
    assert all(set(f.sources) == {"doc:1", "doc:2"} for f in rows)


@pytest.mark.parametrize("change", ["reference", "date", "punctuation", "absent"])
def test_same_property_does_not_merge_different_operations(change):
    docs = dossier()
    if change == "reference": docs[1]["extracted_fields"]["collegamento_operazione"]["riferimento"] = "RP/2026/999"
    if change == "punctuation": docs[1]["extracted_fields"]["collegamento_operazione"]["riferimento"] = "Bologna registro preliminari RP-2026-123"
    if change == "date": docs[1]["extracted_fields"]["collegamento_operazione"]["data"] = "2025-08-01"
    if change == "absent": docs[1]["extracted_fields"].pop("collegamento_operazione")
    assert not comparisons(docs)
    assert not rules(run(docs), "operation_condition_evidence")


@pytest.mark.parametrize("change", ["draft", "unsigned", "citation", "low_confidence", "unknown_confidence", "future", "older", "reference_date"])
def test_unverified_links_cannot_produce_positive_operation_comparison(change):
    docs = dossier()
    fields = docs[1]["extracted_fields"]
    target = fields["collegamento_operazione"]
    if change == "draft": target["stato_documento"] = "bozza"
    if change == "unsigned": target["stato_documento"] = None
    if change == "citation": target["fonte"] = None
    if change == "low_confidence": target["confidence"] = .2
    if change == "unknown_confidence": target["confidence"] = None
    if change == "future": fields["data_atto"] = "2030-01-01"
    if change == "older": fields["data_atto"] = "2020-01-01"
    if change == "reference_date": docs[0]["extracted_fields"]["data"] = "2026-07-01"
    assert not comparisons(docs)
    assert any(f.field == "operazione.verificabilita" for f in run(docs))


@pytest.mark.parametrize("refs", [[unit(sub="2")], [unit(comune="Modena")], [unit(), unit("C/6", sub="2")]])
def test_operation_object_change_is_visible_before_total_price_comparison(refs):
    docs = dossier()
    docs[1]["extracted_fields"]["riferimenti_catastali"] = refs
    assert not comparisons(docs)
    assert any(f.field == "operazione.oggetto" for f in run(docs))


def test_complete_multiunit_bundle_can_be_compared_as_an_operation():
    docs = dossier()
    refs = [unit(), unit("C/6", sub="2")]
    docs[0]["extracted_fields"]["riferimenti_catastali"] = refs
    docs[1]["extracted_fields"]["riferimenti_catastali"] = list(reversed(refs))
    rows = comparisons(docs)
    assert rows and all(f.status == "consistent" for f in rows)
    assert all(len(json.loads(f.scope["unit_set"])) == 2 for f in rows)


@pytest.mark.parametrize("field,value,expected", [("parte_venditrice", ["Luca Neri"], "operazione.venditori"),
    ("parte_acquirente", ["Nora Neri"], "operazione.acquirenti"), ("prezzo_eur", 90000, "operazione.prezzo")])
def test_changes_within_linked_operation_require_reconciliation(field, value, expected):
    docs = dossier()
    docs[1]["extracted_fields"][field] = value
    assert next(f for f in comparisons(docs) if f.field == expected).status == "attention"


def test_missing_or_uncertain_contract_fields_are_not_confirmed():
    docs = dossier()
    docs[1]["extracted_fields"].pop("parte_acquirente")
    docs[1]["extracted_fields"]["prezzo_eur"] = {"valore": 100000, "confidence": .1}
    rows = comparisons(docs)
    assert next(f for f in rows if f.field == "operazione.prezzo").status == "attention"
    assert any(f.field == "operazione.dati_mancanti" for f in rows)


def test_documented_outcome_is_available_evidence_not_automatic_closure():
    docs = dossier()
    findings = run(docs)
    proof = rules(findings, "operation_condition_evidence")[0]
    assert proof.status == "attention" and proof.scope["condition_ref"] == "art. 4"
    assert rules(findings, "contract_conditions")  # the original issue is retained
    plan = build_investigation_plan(91, PROPERTY, docs, findings, TODAY)
    case = next(c for c in plan["cases"] if proof.finding_id in c["finding_ids"])
    assert case["status"] == "review_available_evidence"
    assert not case["automatic_closure"] and case["closure_requirements"]


@pytest.mark.parametrize("change", ["clause", "confidence", "citation", "state", "same_hash", "derived"])
def test_outcome_requires_matching_clause_trace_and_independent_origin(change):
    docs = dossier()
    outcome = docs[1]["extracted_fields"]["condizioni_dettaglio"][0]
    if change == "clause": outcome["identificativo"] = "art. 9"
    if change == "confidence": outcome["confidence"] = .3
    if change == "citation": outcome["fonte"] = None
    if change == "state": outcome["stato"] = "non_determinabile"
    if change == "same_hash":
        for d in docs: d["content_sha256"] = "one-origin"
    if change == "derived": docs[1]["extracted_fields"]["_validation_origin"] = {"document_id": 1}
    assert not rules(run(docs), "operation_condition_evidence")


def test_no_cross_confirmation_from_copied_contract():
    docs = dossier()
    docs[1]["extracted_fields"]["_validation_origin"] = {"document_id": 1}
    assert not any(f.status == "consistent" for f in comparisons(docs))


def test_feedback_changes_operation_link_and_never_resurrects_rejected_link():
    docs = dossier()
    facts = [{"id": "rejected-link", "source_document_id": 2, "fact_name": "collegamento_operazione",
              "fact_value": link(), "verification_status": "rejected"}]
    assert not rules(run(docs, facts=facts), "operation_comparison")


def test_property_coverage_cannot_combine_two_units_ape_fields():
    docs = [doc(1, kind="ape", fields={"classe_energetica": "B"}),
            doc(2, [unit(sub="2")], kind="ape", fields={"data_scadenza": "2030-01-01"})]
    energy = next(row for row in build_validation_coverage(91, PROPERTY, docs, run(docs))["domains"] if row["domain"] == "energy")
    assert energy["status"] == "needs_input"
    assert len(energy["units"]) == 2 and all(u["missing_inputs"] for u in energy["units"])


def test_global_multiunit_fields_remain_unassigned():
    docs = [doc(1, [unit(), unit(sub="2")], kind="ape", fields={"classe_energetica": "C", "data_scadenza": "2030-01-01"})]
    energy = next(row for row in build_validation_coverage(91, PROPERTY, docs, run(docs))["domains"] if row["domain"] == "energy")
    assert energy["unassigned_sources"] == ["doc:1"]
    assert all(u["missing_inputs"] for u in energy["units"])


def finding(fid, domain="category_use", sources=None, confidence=.95, scope=None):
    return CrossValidationFinding(finding_id=fid, property_id=91, rule_id=domain, field="catasto.uso_dichiarato",
        status="attention", severity="high", label="Controlla il dato", detail="Fonte da verificare",
        sources=sources or ["doc:1"], scope=scope or {k: str(v) for k, v in unit().items() if k != "categoria"},
        values=[{"source_key": (sources or ["doc:1"])[0], "value": "C/2", "confidence": confidence}])


def test_reading_is_prerequisite_only_for_checks_using_the_same_source():
    findings = [finding("uncertain", confidence=.1), finding("independent", sources=["doc:2"], scope={**unit(), "subalterno": "2"})]
    plan = build_investigation_plan(91, PROPERTY, [], findings, TODAY)
    reading = next(c for c in plan["cases"] if c["domain"] == "reading")
    dependent = next(c for c in plan["cases"] if c["domain"] == "use" and "uncertain" in c["finding_ids"])
    independent = next(c for c in plan["cases"] if "independent" in c["finding_ids"])
    assert reading["case_id"] in dependent["blocked_by"]
    assert independent["blocked_by"] == []
    assert plan["next_case_id"] == reading["case_id"]


def test_hypotheses_are_explicit_and_cases_are_stable_under_input_order():
    docs = dossier()
    findings = run(docs)
    original = deepcopy((docs, [f.model_dump() for f in findings]))
    first = build_investigation_plan(91, PROPERTY, docs, findings, TODAY)
    second = build_investigation_plan(91, PROPERTY, list(reversed(docs)), list(reversed(findings)), TODAY)
    assert first == second
    assert all(not h["confirmed"] for c in first["cases"] for h in c["possible_explanations"])
    assert (docs, [f.model_dump() for f in findings]) == original
    json.dumps(first, allow_nan=False)


def test_investigation_dates_use_corrected_snapshot_and_api_has_plan(monkeypatch):
    from api import operations_routes
    from api.session import user_client
    from fastapi.testclient import TestClient
    from main_api import app
    docs = dossier()
    facts = [{"id": "date-fix", "source_document_id": 1, "fact_name": "data", "fact_value": "2020-01-01",
              "verification_status": "corrected", "verified_value": "2026-08-01"}]
    docs[0]["extracted_fields"]["data"] = "2020-01-01"
    findings = run(docs, facts=facts)
    monkeypatch.setattr(operations_routes, "_findings", lambda pid, client: (PROPERTY, docs, findings, facts))
    app.dependency_overrides[user_client] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/properties/91/cross-validation")
        assert response.status_code == 200
        plan = response.json()["agent_review"]["investigation_plan"]
        assert plan["cases"]
        assert next(row for row in plan["timeline"] if row["source_key"] == "doc:1")["document_date"] == "2026-08-01"
    finally:
        app.dependency_overrides.clear()


def test_second_reading_checks_operation_identity_but_normalizes_date_format():
    assert extraction_disagreements({"collegamento_operazione": link()}, {"collegamento_operazione": link(riferimento="RP/999")})
    assert not extraction_disagreements({"collegamento_operazione": link()}, {"collegamento_operazione": link(data="01/08/2026")})


def test_operation_findings_include_proof_of_the_link_as_well_as_values():
    docs = dossier()
    rows = comparisons(docs)
    assert all(sum(v["source_path"] == "collegamento_operazione" for v in f.values) == 2 for f in rows)
    proof = rules(run(docs), "operation_condition_evidence")[0]
    assert any(v["source_path"] == "condizioni_dettaglio[0]" and v["source_key"] == "doc:1" for v in proof.values)


@pytest.mark.parametrize("change", ["duplicate_identifier", "uncertain_condition", "uncited_condition"])
def test_uncertain_original_clause_cannot_be_treated_as_matched_outcome(change):
    docs = dossier()
    records = docs[0]["extracted_fields"]["condizioni_dettaglio"]
    if change == "duplicate_identifier": records.append(condition("pendente", descrizione="Altra condizione"))
    if change == "uncertain_condition": records[0]["confidence"] = .1
    if change == "uncited_condition": records[0]["fonte"] = None
    assert not rules(run(docs), "operation_condition_evidence")


def test_conflicting_final_outcomes_do_not_select_the_favorable_one():
    docs = dossier()
    other = deepcopy(docs[1])
    other["id"] = 3
    other["file_name"] = "altro_esito.pdf"
    other["extracted_fields"]["condizioni_dettaglio"] = [condition("non_avverata")]
    docs.append(other)
    findings = run(docs)
    assert not rules(findings, "operation_condition_evidence")
    assert rules(findings, "operation_condition_history")
    assert any("doc:3" in f.sources for f in rules(findings, "contract_conditions"))


def test_technical_cases_get_technical_hypotheses_and_unlinked_contracts_ask_for_context():
    f = finding("technical", domain="technical_scope")
    f.field = "tecnica.difformita"
    docs = dossier()
    docs[1]["extracted_fields"].pop("collegamento_operazione")
    plan = build_investigation_plan(91, PROPERTY, docs, [f], TODAY)
    case = plan["cases"][0]
    assert case["domain"] == "technical" and case["assigned_role"] == "Tecnico"
    assert any("rilievo" in h["how_to_check"] for h in case["possible_explanations"])
    assert plan["context_questions"]
