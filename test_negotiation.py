from datetime import date

from document_engine.checklist import build_checklist
from document_engine.cross_validation import cross_validate
from document_engine.negotiation import build_negotiation_brief

TODAY = date(2026, 9, 23)
PROPERTY = {"id": 1, "is_condominio": True}


def doc(doc_id, kind, fields):
    return {"id": doc_id, "document_type": kind, "file_name": f"{kind}.pdf", "extracted_fields": fields}


def brief(documents):
    findings = cross_validate(1, documents=documents, today=TODAY)
    return build_negotiation_brief(build_checklist(property_record=PROPERTY, documents=documents, findings=findings, today=TODAY))


def texts(entries):
    return " ".join(entry["text"] for entry in entries)


def test_missing_documents_become_questions_and_clauses():
    result = brief([])
    assert "mutui, ipoteche o pignoramenti" in texts(result["questions"])
    assert "libero da ipoteche" in texts(result["clauses"])
    assert "concessione entro una data" in texts(result["clauses"])
    assert result["blockers"] == []


def test_seizure_is_a_blocker():
    result = brief([doc(2, "visura_ipotecaria", {"tipo_formalita": "Pignoramento immobiliare", "formalita_ancora_attiva": True})])
    assert result["blockers"] and result["blockers"][0]["document"] == "Ispezione ipotecaria aggiornata"
    assert "Cancellazione di ipoteche" in texts(result["clauses"])


def test_owner_conflict_asks_who_signs():
    result = brief([
        doc(1, "visura_catastale", {"intestatari": ["Rossi Giovanni", "Rossi Maria"]}),
        doc(3, "atto_di_provenienza", {"avente_causa": ["Rossi Giovanni"], "tipo_provenienza": "compravendita"}),
    ])
    question = next(q for q in result["questions"] if "Firmeranno tutti" in q["text"])
    assert any("soggetti" in reason for reason in question["reasons"])


def test_entries_are_deduplicated_with_all_reasons():
    result = brief([])
    ape_clauses = [c for c in result["clauses"] if "APE" in c["text"]]
    assert len(ape_clauses) == 1
