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
