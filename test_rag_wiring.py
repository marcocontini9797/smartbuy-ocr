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


def test_query_embeddings_are_cached(monkeypatch):
    import numpy as np
    from document_engine import rag_service
    calls = []
    monkeypatch.setattr(rag_service, "_embed", lambda texts: (calls.append(list(texts)), np.ones((len(texts), 3)))[1])
    rag_service._QUERY_CACHE.clear()
    rag_service._embed_queries(["a", "b"])
    out = rag_service._embed_queries(["b", "a", "c"])
    assert calls == [["a", "b"], ["c"]] and out.shape == (3, 3)


class _Table:
    def __init__(self, rows):
        self.rows, self.filters = rows, {}

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, _):
        return self

    @property
    def data(self):
        return [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]

    def execute(self):
        return self


class _Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Table(self.tables[name])


def test_backfill_indexes_only_missing_current_documents(monkeypatch):
    from document_engine import rag_service
    indexed = []
    monkeypatch.setattr(rag_service, "index_uploaded_document",
                        lambda client, **kw: indexed.append(kw["document"]["id"]) or 3)
    client = _Client({
        "document_chunks": [{"document_id": 1}],
        "document_text_extractions": [{"document_id": 1, "raw_text": "x"}, {"document_id": 2, "raw_text": "y"},
                                      {"document_id": 3, "raw_text": "z"}],
        "documents": [{"id": 2, "property_id": 9, "superseded_by": None},
                      {"id": 3, "property_id": 9, "superseded_by": 2}],
    })
    assert rag_service.backfill_missing(client) == {"indexed": 1, "skipped": 1}
    assert indexed == [2]
