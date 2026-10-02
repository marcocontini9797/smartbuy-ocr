import json

from document_engine import agent_llm_gateway as gw
from document_engine.agent_llm_gateway import _cited_sources
from document_engine.rag_service import index_uploaded_document, retrieve_passages


def test_citation_accepts_page_ranges():
    evidence = [{"document": "regolamento.pdf", "page": 2}]
    out = _cited_sources("Vietato (fonte: regolamento.pdf, pagg. 2-3).", evidence)
    assert out == [{"document": "regolamento.pdf", "page": 2}]


def test_services_do_nothing_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert index_uploaded_document(object(), property_id=1, document={"id": 1}, ocr_text="testo") == 0
    assert retrieve_passages(object(), 1, "domanda")["strength"] == "unavailable"


def test_gateway_sends_passages_and_flags_empty_search(monkeypatch):
    seen = {}

    class Out:
        answer = "Sì (fonte: verbale.pdf, pag. 4)."
        confidence = 0.9
        grounded = True

    def fake(**kw):
        seen["payload"] = json.loads(kw["user"])
        return Out()

    monkeypatch.setattr(gw, "structured_call", fake)
    context = {"facts": [{"field": "a", "value": 1}], "evidence": [], "issues": [],
               "passages": [{"fonte": "verbale.pdf", "pagina": 4, "sezione": None, "testo": "x"}],
               "retrieval_strength": "none"}
    response = gw.AgentLLMGateway().complete(task="t", context=context, property_id=1, user_query="q")
    assert seen["payload"]["brani_di_documenti"][0]["fonte"] == "verbale.pdf"
    assert "nota_ricerca" in seen["payload"]
    assert response.sources == [{"document": "verbale.pdf", "page": 4}]
