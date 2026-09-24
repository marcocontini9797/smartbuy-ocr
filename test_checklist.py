from datetime import date

from document_engine.checklist import build_checklist
from document_engine.cross_validation import cross_validate

TODAY = date(2026, 9, 23)
PROPERTY = {"id": 1, "address": "Via Giustiniano 456", "city": "Bologna", "is_condominio": True}


def doc(doc_id, kind, fields):
    return {"id": doc_id, "document_type": kind, "file_name": f"{kind}.pdf", "extracted_fields": fields}


VISURA = doc(1, "visura_catastale", {"intestatari": ["Rossi Giovanni"],
                                     "riferimento": {"comune": "Bologna", "foglio": "285", "particella": "789", "subalterno": "2"},
                                     "data_visura": "2026-09-14"})


def items(result):
    return {item["key"]: item for item in result["items"]}


def test_empty_file_lists_every_document_as_missing():
    result = build_checklist(property_record=PROPERTY, documents=[], findings=[], today=TODAY)
    assert {i["status"] for i in result["items"]} == {"missing"}
    assert result["summary"]["tone"] == "missing"
    assert result["summary"]["missing_required"] == result["summary"]["required_total"] == 6
    assert items(result)["ape"]["action"] == "Richiedere: ape – attestato di prestazione energetica (venditore)"


def test_present_clean_document_is_verified():
    result = build_checklist(property_record=PROPERTY, documents=[VISURA], findings=[], today=TODAY)
    assert items(result)["visura_catastale"]["status"] == "verified"
    assert result["summary"]["required_present"] == 1


def test_seizure_on_visura_ipotecaria_is_a_problem_and_blocks_the_verdict():
    ipotecaria = doc(2, "visura_ipotecaria", {"tipo_formalita": "Pignoramento immobiliare", "formalita_ancora_attiva": True})
    result = build_checklist(property_record=PROPERTY, documents=[VISURA, ipotecaria], findings=[], today=TODAY)
    item = items(result)["visura_ipotecaria"]
    assert item["status"] == "problem"
    assert item["issues"][0]["severity"] == "critica"
    assert result["summary"]["tone"] == "problem"


def test_conflict_between_documents_marks_both_documents():
    atto = doc(3, "atto_di_provenienza", {"avente_causa": ["Bianchi Anna"], "tipo_provenienza": "compravendita"})
    documents = [VISURA, atto]
    findings = cross_validate(1, documents=documents, today=TODAY)
    result = build_checklist(property_record=PROPERTY, documents=documents, findings=findings, today=TODAY)
    assert items(result)["visura_catastale"]["status"] == "problem"
    assert items(result)["atto_di_provenienza"]["status"] == "problem"
    assert any("Proprietari" in issue["title"] for issue in items(result)["atto_di_provenienza"]["issues"])


def test_expired_ape_is_a_problem_of_the_ape():
    ape = doc(4, "APE", {"classe_energetica": "C", "data_emissione": "2014-01-10", "data_scadenza": "2024-01-10"})
    findings = cross_validate(1, documents=[ape], today=TODAY)
    result = build_checklist(property_record=PROPERTY, documents=[ape], findings=findings, today=TODAY)
    assert items(result)["ape"]["status"] == "problem"


def test_condominium_documents_not_applicable_outside_a_condominium():
    result = build_checklist(property_record={**PROPERTY, "is_condominio": False}, documents=[], findings=[], today=TODAY)
    assert items(result)["regolamento_condominio"]["applicable"] is False
    assert result["items"][-1]["key"] in {"regolamento_condominio", "verbale_assemblea_condominio"}


def test_agent_correction_changes_the_red_flags():
    ipotecaria = doc(2, "visura_ipotecaria", {"tipo_formalita": "Pignoramento immobiliare", "formalita_ancora_attiva": True})
    corrected = [{"source_document_id": 2, "fact_name": "formalita_ancora_attiva", "verification_status": "corrected",
                  "verified_value": {"value": False}}]
    before = build_checklist(property_record=PROPERTY, documents=[ipotecaria], findings=[], today=TODAY)
    after = build_checklist(property_record=PROPERTY, documents=[ipotecaria], findings=[], facts=corrected, today=TODAY)
    assert items(before)["visura_ipotecaria"]["status"] == "problem"
    assert items(after)["visura_ipotecaria"]["status"] == "verified"


def test_commercial_checklist_requires_agibilita_and_systems_and_asks_for_lease():
    result = build_checklist(property_record={**PROPERTY, "property_type": "commerciale"}, documents=[], findings=[], today=TODAY)
    by_key = items(result)
    assert by_key["certificato_agibilita"]["requirement"] == "required"
    assert by_key["dichiarazione_conformita_impianti"]["requirement"] == "required"
    assert by_key["contratto_locazione"]["requirement"] == "leased"
    assert result["summary"]["required_total"] == 8
    assert "commerciale" in result["note"]


def test_shop_registered_as_dwelling_is_a_problem():
    visura = doc(1, "visura_catastale", {"riferimento": {"foglio": "1", "categoria": "A/2"}})
    shop = build_checklist(property_record={**PROPERTY, "property_type": "commerciale"}, documents=[visura], findings=[], today=TODAY)
    flat = build_checklist(property_record=PROPERTY, documents=[visura], findings=[], today=TODAY)
    assert items(shop)["visura_catastale"]["status"] == "problem"
    assert "A/2" in items(shop)["visura_catastale"]["issues"][0]["title"]
    assert items(flat)["visura_catastale"]["status"] == "verified"


def test_commercial_lease_red_flags_attach_to_the_lease():
    lease = doc(5, "contratto_locazione", {"uso": "commerciale", "registrato": False, "canone_mensile_eur": {"valore": "1200"}})
    result = build_checklist(property_record={**PROPERTY, "property_type": "commerciale"}, documents=[lease], findings=[], today=TODAY)
    assert items(result)["contratto_locazione"]["status"] == "problem"


def test_residential_lease_needs_ape_and_visura_not_the_deed():
    result = build_checklist(property_record={**PROPERTY, "contract": "affitto"}, documents=[], findings=[], today=TODAY)
    required = {i["key"] for i in result["items"] if i["requirement"] == "required"}
    assert required == {"visura_catastale", "ape"}
    assert "atto_di_provenienza" not in items(result) and result["contract"] == "affitto"
    assert result["note"].startswith("Checklist operativa per l'affitto di appartamento")


def test_commercial_lease_requires_use_agibilita_and_systems():
    record = {**PROPERTY, "property_type": "commerciale", "typology": "ufficio", "contract": "affitto"}
    required = {i["key"] for i in build_checklist(property_record=record, documents=[], findings=[], today=TODAY)["items"]
                if i["requirement"] == "required"}
    assert {"titolo_edilizio", "certificato_agibilita", "dichiarazione_conformita_impianti"} <= required


def test_box_sale_has_no_ape():
    result = build_checklist(property_record={**PROPERTY, "typology": "box"}, documents=[], findings=[], today=TODAY)
    assert "ape" not in items(result) and result["summary"]["required_total"] == 4


def test_pertinenze_in_the_visura_are_not_a_category_problem():
    visura = doc(9, "visura_catastale", {"riferimenti_catastali": [{"foglio": "1", "particella": "2", "subalterno": "3", "categoria": "A/2"},
                                                                    {"foglio": "1", "particella": "2", "subalterno": "9", "categoria": "C/6"}]})
    result = build_checklist(property_record=PROPERTY, documents=[visura], findings=[], today=TODAY)
    assert not any("Categoria catastale" in issue["title"] for issue in items(result)["visura_catastale"]["issues"])
    office = build_checklist(property_record={**PROPERTY, "typology": "ufficio", "property_type": "commerciale"},
                             documents=[visura], findings=[], today=TODAY)
    assert any("A/2" in issue["title"] for issue in items(office)["visura_catastale"]["issues"])
