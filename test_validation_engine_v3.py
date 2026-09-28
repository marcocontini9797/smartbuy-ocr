"""Adversarial synthetic cases: no model calls, network or customer documents."""
from copy import deepcopy
import json

import pytest

from document_engine.agent_review import build_agent_review
from document_engine.cross_validation import extraction_disagreements
from document_engine.validation_coverage import build_validation_coverage
from document_engine.validation_rules import effective_documents
from test_validation_engine_v2 import TODAY, PROPERTY, doc, unit, run, rules


def parties(buyer="Giovanni Rossi", owner="Rossi Giovanni", *, acquired="2020-01-01", observed="2026-09-27", **extras):
    return [doc(1, kind="atto_compravendita", fields={"parte_venditrice": ["Anna Bianchi"], "parte_acquirente": [buyer], "data_atto": acquired}),
            doc(2, fields={"intestatari": [owner], "data_visura": observed}, **extras)]


def test_deed_buyer_compared_with_later_visura_but_old_seller_never_as_owner():
    findings = run(parties())
    role = rules(findings, "party_roles")[0]
    assert role.status == "consistent"
    assert {v["source_path"] for v in role.values} == {"parte_acquirente", "intestatari"}
    assert "non prova proprietà" in role.detail
    assert role.scope["subalterno"] == "1"
    assert not any(f.field == "proprietari" and f.status == "conflict" for f in findings)


@pytest.mark.parametrize("acquired,observed", [(None, "2026-01-01"), ("2020-01-01", None), ("2026-01-01", "2020-01-01"), ("2020-01-01", "2030-01-01")])
def test_acquisition_comparison_needs_valid_chronology(acquired, observed):
    assert rules(run(parties(acquired=acquired, observed=observed)), "party_roles")[0].status == "attention"


@pytest.mark.parametrize("owner", ["Luca Verdi", "Rossi", "Giovanni Rossi e Maria Rossi"])
def test_different_or_partial_names_need_review_not_a_legal_ownership_verdict(owner):
    assert rules(run(parties(owner=owner)), "party_roles")[0].status == "attention"


@pytest.mark.parametrize("variation", ["other_unit", "other_comune", "incomplete", "multiple"])
def test_parties_from_unmatched_units_are_not_compared(variation):
    docs = parties()
    refs = {"other_unit": [unit(sub="2")], "other_comune": [unit(comune="Modena")],
            "incomplete": [{"foglio": "10"}], "multiple": [unit(), unit(sub="2")]}[variation]
    docs[1]["extracted_fields"]["riferimenti_catastali"] = refs
    findings = rules(run(docs), "party_roles")
    assert all(f.status != "consistent" for f in findings)
    assert any(f.field == "titolarita.ambito" for f in findings)


def test_role_match_requires_independent_sources_and_reliable_reading():
    docs = parties()
    docs[1]["extraction_confidence"] = .1
    assert rules(run(docs), "party_roles")[0].status == "attention"
    docs = parties()
    for d in docs:
        d["content_sha256"] = "same-origin"
    assert not any(f.status == "consistent" for f in rules(run(docs), "party_roles"))


def test_landlord_difference_does_not_assert_illegal_ownership():
    docs = [doc(fields={"intestatari": ["Mario Rossi"]}),
            doc(2, kind="contratto_locazione", fields={"locatore": ["Anna Bianchi"]})]
    item = rules(run(docs), "party_roles")[0]
    assert item.field == "titolarita.locatore" and item.status == "attention"


def title(person="Mario Rossi", right="proprieta", quota="1/2", **extras):
    return {"soggetto": person, "diritto": right, "quota": quota, "fonte": "pag. 2", "confidence": .95, **extras}


def test_shares_separated_by_right_and_unit():
    records = [title(quota="1/1"), title("Anna Bianchi", "usufrutto", "1/1"),
               title("Luca Verdi", quota="1/1", riferimento=unit(sub="2"))]
    assert not rules(run([doc(fields={"titolarita": records, "elenco_titolari_completo": True})]), "ownership_rights")


@pytest.mark.parametrize("quota", ["3/2", "0/1", "1/0", "-1/2", "50/0", "non leggibile", None])
def test_malformed_structured_shares_are_reviewable(quota):
    assert rules(run([doc(fields={"titolarita": [title(quota=quota)]})]), "ownership_rights")


def test_partial_share_list_is_not_assumed_complete():
    fields = {"titolarita": [title()]}
    assert not rules(run([doc(fields=fields)]), "ownership_rights")
    assert rules(run([doc(fields={**fields, "elenco_titolari_completo": True})]), "ownership_rights")


def test_share_duplicates_do_not_count_twice_and_disagreement_needs_review():
    fields = {"titolarita": [title(quota="1/1"), title("Rossi Mario", quota="1/1")]}
    assert not rules(run([doc(fields=fields)]), "ownership_rights")
    fields["titolarita"][1]["quota"] = "1/2"
    assert rules(run([doc(fields=fields)]), "ownership_rights")


def test_free_text_rights_are_not_compared_as_first_fraction():
    docs = [doc(fields={"diritti_e_quote": "Mario proprietà 1/2; Anna proprietà 1/2"}),
            doc(2, fields={"diritti_e_quote": "Luca usufrutto 1/1"})]
    assert not any(f.field == "quota_proprieta" for f in run(docs))


def formality(state="attiva", identifier="Bologna 2026 RP 77", **extras):
    return {"identificativo": identifier, "tipo": "ipoteca", "stato": state, "confidence": .95, "fonte": "nota pag. 3", **extras}


@pytest.mark.parametrize("state", ["attiva", "cancellazione_parziale", "cancellazione_richiesta", "non_determinabile", None])
def test_formality_unresolved_states_are_never_clearance(state):
    findings = rules(run([doc(kind="visura_ipotecaria", fields={"formalita": [formality(state)]})]), "encumbrances")
    assert findings and all(f.status == "attention" for f in findings)
    assert findings[0].values[0]["source_text"] == "nota pag. 3"


def test_cancellation_reconciles_only_same_note_and_unit():
    active = doc(kind="visura_ipotecaria", fields={"formalita": [formality()]})
    cancelled = doc(2, kind="visura_ipotecaria", fields={"formalita": [formality("cancellata")]})
    assert any(f.field.startswith("vincoli.stato.") for f in run([active, cancelled]))
    cancelled["extracted_fields"]["formalita"][0]["identificativo"] = "Bologna 2026 RP 78"
    assert not any(f.field.startswith("vincoli.stato.") for f in run([active, cancelled]))
    cancelled["extracted_fields"]["formalita"][0] = formality("cancellata", riferimento=unit(sub="2"))
    assert not any(f.field.startswith("vincoli.stato.") for f in run([active, cancelled]))


def test_mortgage_mentioned_in_old_deed_does_not_become_active_lien():
    assert not rules(run([doc(kind="atto_compravendita", fields={"presenza_mutuo_ipoteca": True})]), "encumbrances")
    assert rules(run([doc(kind="visura_ipotecaria", fields={"formalita_ancora_attiva": True})]), "encumbrances")


def test_free_property_and_lease_require_actual_release_evidence():
    prop = {**PROPERTY, "workflow_context": {"occupancy": "vacant"}}
    findings = rules(run([doc(kind="contratto_locazione", fields={"data_fine": "2020-01-01"})], prop), "occupancy")
    assert any(f.field == "locazione.disponibilita" for f in findings)
    assert "non dimostra" in findings[0].detail
    assert not any(f.field == "ape.scadenza" for f in findings)


@pytest.mark.parametrize("registered,expected", [(False, True), (True, False), (None, False), ("no", True)])
def test_lease_registration_uses_explicit_status(registered, expected):
    findings = run([doc(kind="contratto_locazione", fields={"registrato": registered})])
    assert any(f.field == "locazione.registrazione" for f in findings) == expected


@pytest.mark.parametrize("state,flagged", [("pendente", True), ("non_avverata", True), (None, True), ("avverata", False), ("rinunciata", False)])
def test_conditions_follow_documented_status_without_inventing_contract_expiry(state, flagged):
    condition = {"identificativo": "art-4", "descrizione": "Ottenimento finanziamento", "stato": state,
                 "data_scadenza": "2026-09-01", "fonte": "art. 4", "confidence": .9}
    findings = rules(run([doc(kind="preliminare_compravendita", fields={"condizioni_dettaglio": [condition]})]), "contract_conditions")
    assert bool(findings) == flagged
    if flagged:
        assert "oltre il termine" in findings[0].label
        assert "non viene dedotta" in findings[0].detail.lower()


def test_plain_conditions_need_outcome_and_past_deed_deadline_needs_update():
    findings = rules(run([doc(kind="preliminare_compravendita", fields={
        "condizioni_sospensive": ["Concessione mutuo"], "termine_rogito": "2026-09-01"})]), "contract_conditions")
    assert {f.field for f in findings} == {"trattativa.condizioni", "trattativa.termine_rogito"}


def test_condominium_arrears_are_not_assigned_to_seller_without_proof():
    item = rules(run([doc(kind="verbale_assemblea_condominio", fields={"morosita_menzionata": True})]), "condominium")[0]
    assert "non è automaticamente un debito" in item.detail


@pytest.mark.parametrize("share,confidence,expected", [(1200, .95, "conflict"), (1200, .1, "attention"), (-10, .9, "conflict"), (100, .9, None)])
def test_condominium_amount_relation_retains_reading_confidence(share, confidence, expected):
    findings = rules(run([doc(kind="verbale_assemblea_condominio", fields={"delibere": [
        {"oggetto": "Tetto", "importo_totale_eur": 1000, "quota_a_carico_unita_eur": share, "confidence": confidence}]})]), "condominium")
    assert (findings[0].status if findings else None) == expected


@pytest.mark.parametrize("state,flagged", [("in istruttoria", True), ("decaduto", True), ("in sanatoria", True), ("rilasciato", False), (None, False)])
def test_pending_building_application_is_not_treated_as_approved(state, flagged):
    assert bool(rules(run([doc(kind="titolo_edilizio", fields={"stato": state})]), "technical_scope")) == flagged


def test_positive_overall_conformity_does_not_hide_reported_defects():
    findings = rules(run([doc(kind="relazione_tecnica_integrata", fields={
        "conformita_catastale": True, "conformita_urbanistica": True,
        "difformita_riscontrate": ["Tramezzo da verificare"], "difformita_rientrano_in_tolleranza": None})]), "technical_scope")
    assert findings[0].field == "tecnica.difformita"


@pytest.mark.parametrize("mode", ["sandbox", "simulation", "fixture", "demo"])
def test_simulated_sources_cannot_generate_real_transaction_findings_or_coverage(mode):
    docs = [doc(kind="visura_ipotecaria", fields={"formalita": [formality()]}, source_mode=mode)]
    findings = run(docs)
    assert not rules(findings, "encumbrances")
    coverage = build_validation_coverage(91, PROPERTY, docs, findings)
    assert not any(row["sources"] for row in coverage["domains"])


def test_coverage_does_not_turn_empty_file_into_completed_review():
    review = build_agent_review(91, PROPERTY, [], [])
    assert all(d["status"] == "needs_input" for d in review["coverage"]["domains"])
    assert review["questions"] and review["assessment"] == "needs_review"


def test_lease_expiry_does_not_satisfy_energy_coverage_and_false_is_not_missing():
    docs = [doc(kind="contratto_locazione", fields={"data_scadenza": "2030-01-01", "registrato": False, "locatore": ["Rossi"], "conduttore": ["Bianchi"]})]
    coverage = build_validation_coverage(91, {**PROPERTY, "workflow_context": {"occupancy": "leased"}}, docs, run(docs))
    energy = next(d for d in coverage["domains"] if d["domain"] == "energy")
    lease = next(d for d in coverage["domains"] if d["domain"] == "occupancy")
    assert energy["status"] == "needs_input" and energy["sources"] == []
    assert lease["missing_inputs"] == [] and lease["status"] == "needs_review"


def test_alias_correction_is_respected_in_scoped_comparisons_and_coverage():
    docs = [doc(fields={"energy_class": "B"}), doc(2, fields={"classe_energetica": "C"}), doc(3, [unit(sub="2")])]
    facts = [{"id": "old", "source_document_id": 1, "fact_name": "energy_class", "fact_value": "B"},
             {"id": "fix", "source_document_id": 1, "fact_name": "classe_energetica", "fact_value": "B",
              "verified_value": "C", "verification_status": "corrected", "evidence_ids": ["e1"]}]
    snapshot = deepcopy((docs, facts))
    assert effective_documents(docs, facts) == effective_documents(docs, list(reversed(facts)))
    energy = [f for f in run(docs, facts=facts) if f.field == "classe_energetica"]
    assert energy and all(f.status == "consistent" for f in energy)
    assert any("e1" in f.evidence_ids for f in energy)
    assert (docs, facts) == snapshot


@pytest.mark.parametrize("key", ["parte_venditrice", "parte_acquirente", "avente_causa", "locatore", "conduttore"])
def test_second_reading_still_checks_each_party_role(key):
    assert extraction_disagreements({key: ["Mario Rossi"]}, {key: ["Anna Bianchi"]})
    assert not extraction_disagreements({key: ["Mario Rossi"]}, {key: ["Rossi Mario"]})


def test_second_reading_structured_records_ignore_order_and_citation_format():
    first = {"titolarita": [title(), title("Anna Bianchi")]}
    second = {"titolarita": [title("Anna Bianchi", fonte="altra pagina"), title(quota="50%", confidence=.5)]}
    assert not extraction_disagreements(first, second)
    assert extraction_disagreements({"formalita": [formality()]}, {"formalita": [formality("cancellata")]})


def test_new_schemas_are_optional_and_validate_existing_documents():
    from schemas import VisuraCatastale, VisuraIpotecaria, PreliminareCompravendita, ContrattoLocazione
    assert VisuraCatastale(intestatari=["Mario Rossi"]).titolarita == []
    assert VisuraCatastale(titolarita=[title()]).titolarita[0].quota == "1/2"
    assert VisuraIpotecaria(formalita=[formality()]).formalita[0].stato == "attiva"
    assert PreliminareCompravendita().condizioni_dettaglio == []
    assert ContrattoLocazione().data_fine is None


def test_trace_serialization_stable_ids_and_action_linkage():
    docs = parties(owner="Anna Bianchi") + [doc(3, kind="visura_ipotecaria", fields={"formalita": [formality()]})]
    findings = run(docs)
    assert {f.finding_id for f in findings} == {f.finding_id for f in run(list(reversed(docs)))}
    review = build_agent_review(91, PROPERTY, docs, findings)
    assert {"authority", "encumbrances"} <= {a["rule_id"] for a in review["actions"]}
    ids = {f.finding_id for f in findings}
    assert all(set(a["finding_ids"]) <= ids for a in review["actions"])
    json.dumps({"findings": [f.model_dump(mode="json") for f in findings], "review": review}, allow_nan=False)


def test_invalid_nested_condition_date_and_partial_detail_are_visible():
    docs = [doc(kind="preliminare_compravendita", fields={
        "condizioni_sospensive": ["Mutuo", "Esito verifica tecnica"],
        "condizioni_dettaglio": [{"identificativo": "mutuo", "stato": "avverata", "data_scadenza": "2026-02-31"}]})]
    findings = rules(run(docs), "contract_conditions")
    assert any(f.field == "trattativa.condizioni" for f in findings)
    assert any("Data della condizione" in f.label for f in findings)


@pytest.mark.parametrize("summary,state", [(True, "cancellata"), (False, "attiva")])
def test_structured_and_summary_lien_status_cannot_silently_disagree(summary, state):
    docs = [doc(kind="visura_ipotecaria", fields={"formalita_ancora_attiva": summary, "formalita": [formality(state)]})]
    assert any(f.field == "vincoli.riepilogo" for f in run(docs))


def test_corrected_role_flows_through_real_api_comparison_and_provenance(monkeypatch):
    from fastapi.testclient import TestClient
    from api import operations_routes
    from api.session import user_client
    from main_api import app
    docs = parties(buyer="Anna Bianchi")
    fact = {"id": "f-party", "provenance_id": "p-party", "fact_name": "parte_acquirente",
            "fact_value": ["Anna Bianchi"], "verified_value": ["Giovanni Rossi"],
            "verification_status": "corrected", "evidence_ids": ["e-party"]}
    provenance = {"p-party": {"document_id": 1, "source_page": 4, "source_text": "Acquista Giovanni Rossi"}}
    monkeypatch.setattr(operations_routes, "_validation_sources", lambda pid, client: (PROPERTY, [fact], docs, provenance))
    app.dependency_overrides[user_client] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/properties/91/cross-validation")
        assert response.status_code == 200
        role = next(f for f in response.json()["findings"] if f["rule_id"] == "party_roles")
        assert role["status"] == "consistent"
        value = next(v for v in role["values"] if v["fact_id"] == "f-party")
        assert value["page"] == 4 and value["source_text"] == "Acquista Giovanni Rossi"
        assert role["evidence_ids"] == ["e-party"]
        assert response.json()["agent_review"]["coverage"]["version"] == "3.1"
    finally:
        app.dependency_overrides.clear()
