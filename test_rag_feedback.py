from document_engine.rag_calibration import calibration_report
from document_engine.rag_search import Passage, RetrievalConfig, apply_hints, retrieve
from document_engine.rag_store import MemoryChunkStore
import numpy as np


def passage(cid, similarity=0.5, relevance=None, score=0.1, index=0):
    return Passage(chunk_id=cid, document_id=1, document_name="d.pdf", document_type="atto", chunk_index=index,
                   page_start=1, page_end=1, heading=None, text=cid, similarity=similarity, relevance=relevance, score=score)


def test_validated_chunk_is_promoted_and_rejected_one_demoted():
    config = RetrievalConfig()
    ranked = [passage("a", relevance=0.9, score=0.3, index=0), passage("b", relevance=0.7, score=0.2, index=1),
              passage("c", relevance=0.7, score=0.1, index=2)]
    out, applied = apply_hints(ranked, {"c": 1.0, "a": -1.0}, config, reranked=True)
    assert applied == 2
    assert [p.chunk_id for p in out][0] == "c"            # validated: lifted to strong relevance
    assert out[-1].chunk_id == "a" and out[-1].relevance < 0.5      # rejected: demoted, not removed


def test_validated_chunk_missing_from_candidates_is_added():
    out, applied = apply_hints([passage("a", relevance=0.4)], {"z": 2.0}, RetrievalConfig(), True, {"z": passage("z")})
    assert applied == 1 and {p.chunk_id for p in out} == {"a", "z"}
    assert max(out, key=lambda p: p.relevance or 0).chunk_id == "z"


def test_unknown_chunks_are_ignored():
    out, applied = apply_hints([passage("a")], {"nope": 1.0}, RetrievalConfig(), False)
    assert applied == 0 and [p.chunk_id for p in out] == ["a"]


class HintedStore(MemoryChunkStore):
    def __init__(self, hints):
        super().__init__()
        self.hints = hints

    def feedback_hints(self, property_id, embedding, min_similarity):
        return self.hints

    def chunks_by_id(self, property_id, ids):
        return []


def test_retrieve_applies_feedback_and_keeps_the_question_vector():
    store = HintedStore({})
    for i, text in enumerate(["ipoteca iscritta a favore della banca", "spese condominiali arretrate"]):
        store.add(property_id=1, document_id=1, document_name="d.pdf", document_type="atto", chunk_index=i,
                  page_start=1, page_end=1, heading=None, content=text, context="", embedding=[1.0 - i, float(i), 0.0])
    embed = lambda texts: np.array([[1.0, 0.0, 0.0] for _ in texts])
    plain = retrieve(store, embed, 1, "ipoteca banca")
    store.hints = {"1:1": -1.0, "1:0": 1.0}
    hinted = retrieve(store, embed, 1, "ipoteca banca")
    assert plain.hints_applied == 0 and hinted.hints_applied == 2
    assert hinted.vector == [1.0, 0.0, 0.0]


def rows(useful, bad):
    return ([{"rating": 1, "strength": "strong", "best_relevance": v} for v in useful]
            + [{"rating": -1, "strength": "weak", "best_relevance": v} for v in bad])


def test_calibration_needs_enough_ratings():
    report = calibration_report(rows([0.9] * 3, [0.3] * 3))
    assert report["suggestion"] is None and "insufficienti" in report["note"]


def test_calibration_suggests_floor_between_the_groups():
    report = calibration_report(rows([0.8 + i * 0.01 for i in range(20)], [0.2 + i * 0.02 for i in range(20)]))
    assert 0.7 <= report["suggestion"]["weak"] <= 0.85
    assert report["suggestion"]["bad_answers_refused"] == 1.0
