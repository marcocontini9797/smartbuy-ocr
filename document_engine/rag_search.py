"""Hybrid retrieval over the chunk index of one property.

Pure logic: the chunk store, the embedder and the optional language-model steps
(query expansion, reranking) are injected, so the same code runs against
Supabase in production and against an in-memory store in tests and evaluation.

What it does beyond "top-k by similarity":

* weighted reciprocal-rank fusion of semantic and lexical ranks, with more
  weight on the lexical side when the question carries identifiers (parcel
  numbers, categories, amounts), which embeddings are weakest at;
* optional phrasings of a short question, fused as additional ranked lists;
* optional model reranking of the fused candidates;
* a relevance gate: when nothing retrieved is relevant the result says so
  (``strength == "none"``) instead of handing the model unrelated passages;
* at most a few chunks per document, the neighbouring chunks of each hit
  for continuity, and the result in reading order.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

import numpy as np

EMBED_DIMENSIONS = 1536
RRF_K = 10

# Calibrated on evaluation/evaluate_rag.py (see DOCUMENT_RAG.md).
STRONG_SIMILARITY = 0.42
WEAK_SIMILARITY = 0.30
STRONG_RELEVANCE = 0.85
WEAK_RELEVANCE = 0.65

_STOPWORDS = frozenset("""
il lo la i gli le un uno una di a da in con su per tra fra e ed o ma se che chi cui non
del dello della dei degli delle al allo alla ai agli alle dal dallo dalla dai dagli dalle
nel nello nella nei negli nelle sul sullo sulla sui sugli sulle ci come quale quali quanto
quanti quanta quante dove quando cosa ho ha hanno essere questo questa questi queste quello
quella suo sua suoi sue mio mia loro anche piu molto poco tutto tutti ogni sono era stato
stata fa fare viene vengono puo possono deve devono c l d s
""".split())
_TOKEN = re.compile(r"[a-z0-9]+")


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()


def lexical_terms(question: str, limit: int = 24) -> list[str]:
    """Content words and numbers of a question, accents removed, duplicates dropped."""
    seen: dict[str, None] = {}
    for token in _TOKEN.findall(_plain(question)):
        if token in _STOPWORDS or (len(token) < 2 and not token.isdigit()):
            continue
        seen.setdefault(token, None)
    return list(seen)[:limit]


def tsquery_or(terms: Sequence[str]) -> str:
    """Terms as an OR full-text query. Natural-language questions rarely match all of
    their words in one chunk, so an AND query would return nothing."""
    return " | ".join(term for term in terms if _TOKEN.fullmatch(term))


@dataclass(frozen=True)
class QueryProfile:
    terms: list[str]
    identifiers: list[str]    # numbers and codes: matched exactly, the lexical side is trusted more
    short: bool               # few content words: a single embedding is unreliable, rephrasing helps


def analyze_query(question: str) -> QueryProfile:
    terms = lexical_terms(question)
    identifiers = [t for t in terms if any(c.isdigit() for c in t)]
    return QueryProfile(terms=terms, identifiers=identifiers, short=len(terms) <= 4 and not identifiers)


@dataclass
class Passage:
    chunk_id: str
    document_id: int
    document_name: str | None
    document_type: str | None
    chunk_index: int
    page_start: int
    page_end: int
    heading: str | None
    text: str
    context: str = ""
    similarity: float = 0.0
    score: float = 0.0
    relevance: float | None = None
    neighbor: bool = False

    @property
    def pages(self) -> str:
        return str(self.page_start) if self.page_start == self.page_end else f"{self.page_start}-{self.page_end}"


class ChunkStore(Protocol):
    def search(self, property_id: int, embedding: Sequence[float], lexical_query: str, limit: int) -> list[dict[str, Any]]:
        """Rows with the columns of smartbuy_search_chunks (similarity, sem_rank, lex_rank...)."""

    def neighbors(self, property_id: int, wanted: list[tuple[int, int]]) -> list[dict[str, Any]]:
        """Chunks (document_id, chunk_index) with their text, pages and heading."""


Embedder = Callable[[list[str]], np.ndarray]
Expander = Callable[[str], list[str]]
Reranker = Callable[[str, list[Passage]], dict[int, float]]    # position in the list -> relevance 0..1


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 6
    candidate_k: int = 24
    neighbors: int = 1
    max_per_document: int = 4
    rrf_k: int = RRF_K
    expansion_weight: float = 0.5
    semantic_weight: float = 1.0
    lexical_weight: float = 1.0
    identifier_boost: float = 0.75       # added to the lexical weight when the question has identifiers
    strong_similarity: float = STRONG_SIMILARITY
    weak_similarity: float = WEAK_SIMILARITY
    strong_relevance: float = STRONG_RELEVANCE
    weak_relevance: float = WEAK_RELEVANCE
    hint_similarity: float = 0.88        # how close an earlier, rated question must be to count


@dataclass
class Retrieval:
    passages: list[Passage]                # what the model is given, in reading order, neighbours included
    strength: str                          # "strong" | "weak" | "none"
    best_similarity: float
    queries: list[str]
    reasons: list[str] = field(default_factory=list)
    ranked: list[Passage] = field(default_factory=list)    # the hits themselves, best first
    best_relevance: float | None = None                    # of the top 3, when a reranker ran
    vector: list[float] | None = None                      # embedding of the question, kept for the feedback trace
    hints_applied: int = 0                                 # chunks moved up or down by earlier feedback


def _passage(row: dict[str, Any]) -> Passage:
    return Passage(
        chunk_id=str(row.get("chunk_id") or row.get("id") or f"{row['document_id']}:{row['chunk_index']}"),
        document_id=int(row["document_id"]), document_name=row.get("document_name"),
        document_type=row.get("document_type"), chunk_index=int(row["chunk_index"]),
        page_start=int(row.get("page_start") or 1), page_end=int(row.get("page_end") or row.get("page_start") or 1),
        heading=row.get("heading"), text=row.get("content") or row.get("text") or "", context=row.get("context") or "",
        similarity=float(row.get("similarity") or 0.0),
    )


def fuse(variants: list[tuple[float, list[dict[str, Any]]]], config: RetrievalConfig, has_identifiers: bool) -> list[Passage]:
    """Weighted reciprocal-rank fusion of the semantic and lexical ranks of every
    phrasing of the question. Fusing ranks instead of raw scores avoids tuning
    two incomparable scales; rows come with the rank each list gave them."""
    lexical_weight = config.lexical_weight + (config.identifier_boost if has_identifiers else 0.0)
    merged: dict[str, Passage] = {}
    for weight, rows in variants:
        for row in rows:
            candidate = _passage(row)
            passage = merged.setdefault(candidate.chunk_id, candidate)
            passage.similarity = max(passage.similarity, float(row.get("similarity") or 0.0))
            if row.get("sem_rank") is not None:
                passage.score += weight * config.semantic_weight / (config.rrf_k + int(row["sem_rank"]))
            if row.get("lex_rank") is not None:
                passage.score += weight * lexical_weight / (config.rrf_k + int(row["lex_rank"]))
    return sorted(merged.values(), key=lambda p: (-p.score, p.document_id, p.chunk_index))


def _identifier_hit(passages: Sequence[Passage], identifiers: Sequence[str]) -> bool:
    """Every identifier of the question appears in one of the best passages: an exact match
    is strong evidence even when the embedding similarity is unremarkable."""
    if not identifiers:
        return False
    for passage in passages:
        tokens = set(_TOKEN.findall(_plain(f"{passage.context} {passage.text}")))
        if all(identifier in tokens for identifier in identifiers):
            return True
    return False


def judge(ranked: Sequence[Passage], profile: QueryProfile, config: RetrievalConfig, reranked: bool) -> tuple[str, list[str]]:
    if not ranked:
        return "none", ["no_candidates"]
    head = ranked[:3]
    reasons: list[str] = []
    if _identifier_hit(head, profile.identifiers):
        return "strong", ["exact_identifier_match"]
    if reranked:
        best = max((p.relevance or 0.0) for p in head)
        reasons.append(f"best_relevance={best:.2f}")
        if best >= config.strong_relevance:
            return "strong", reasons
        return ("weak" if best >= config.weak_relevance else "none"), reasons
    best = max(p.similarity for p in head)
    reasons.append(f"best_similarity={best:.2f}")
    if best >= config.strong_similarity:
        return "strong", reasons
    return ("weak" if best >= config.weak_similarity else "none"), reasons


def _limit_per_document(ranked: Sequence[Passage], top_k: int, per_document: int) -> list[Passage]:
    chosen: list[Passage] = []
    counts: dict[int, int] = {}
    for passage in ranked:
        if counts.get(passage.document_id, 0) >= per_document:
            continue
        counts[passage.document_id] = counts.get(passage.document_id, 0) + 1
        chosen.append(passage)
        if len(chosen) == top_k:
            break
    return chosen


def _with_neighbors(store: ChunkStore, property_id: int, chosen: list[Passage], radius: int) -> list[Passage]:
    if radius <= 0 or not chosen:
        return chosen
    have = {(p.document_id, p.chunk_index) for p in chosen}
    wanted = sorted({(p.document_id, p.chunk_index + step) for p in chosen for step in range(-radius, radius + 1)
                     if step and p.chunk_index + step >= 0} - have)
    if not wanted:
        return chosen
    info = {p.document_id: p for p in chosen}
    extra: list[Passage] = []
    for row in store.neighbors(property_id, wanted):
        source = info.get(int(row["document_id"]))
        extra.append(Passage(
            chunk_id=str(row.get("id") or f"{row['document_id']}:{row['chunk_index']}"),
            document_id=int(row["document_id"]), document_name=source.document_name if source else None,
            document_type=source.document_type if source else None, chunk_index=int(row["chunk_index"]),
            page_start=int(row.get("page_start") or 1), page_end=int(row.get("page_end") or 1),
            heading=row.get("heading"), text=row.get("content") or "", context=row.get("context") or "", neighbor=True,
        ))
    return chosen + extra


def apply_hints(ranked: list[Passage], hints: dict[str, float], config: RetrievalConfig, reranked: bool,
                extra: dict[str, Passage] | None = None) -> tuple[list[Passage], int]:
    """Earlier feedback on similar questions of the same fascicolo. `hints` maps a chunk id to
    the net rating (positive: an answer built on it was marked useful). A validated chunk is
    treated as strong evidence (and added if it was not among the candidates); a rejected one
    is demoted, never removed: the fascicolo may since have gained the right document."""
    applied = 0
    by_id = {p.chunk_id: p for p in ranked}
    for chunk_id, net in hints.items():
        passage = by_id.get(chunk_id) or (extra or {}).get(chunk_id)
        if passage is None or net == 0:
            continue
        if passage.chunk_id not in by_id:
            ranked.append(passage)
            by_id[passage.chunk_id] = passage
        applied += 1
        if net > 0:
            passage.score += 1.0
            passage.similarity = max(passage.similarity, config.strong_similarity)
            if reranked:
                passage.relevance = max(passage.relevance or 0.0, config.strong_relevance)
        else:
            passage.score *= 0.5
            passage.similarity *= 0.7
            if reranked:
                passage.relevance = (passage.relevance or 0.0) * 0.5
    ranked.sort(key=lambda p: (-(p.relevance or 0.0) if reranked else 0.0, -p.score, p.document_id, p.chunk_index))
    return ranked, applied


def retrieve(store: ChunkStore, embed: Embedder, property_id: int, question: str, *,
             expand: Expander | None = None, rerank: Reranker | None = None,
             config: RetrievalConfig = RetrievalConfig()) -> Retrieval:
    profile = analyze_query(question)
    queries = [question]
    if expand is not None and profile.short:
        queries += [q for q in expand(question) if q and q.strip() and q != question]
    vectors = embed(queries)
    variants: list[tuple[float, list[dict[str, Any]]]] = []
    for position, (query, vector) in enumerate(zip(queries, vectors)):
        terms = profile.terms if position == 0 else lexical_terms(query)
        rows = store.search(property_id, list(map(float, vector)), tsquery_or(terms), config.candidate_k)
        variants.append((1.0 if position == 0 else config.expansion_weight, rows))

    ranked = fuse(variants, config, bool(profile.identifiers))[: config.candidate_k]
    reranked = False
    if rerank is not None and len(ranked) > 1:
        scores = rerank(question, ranked)
        if scores:
            for position, passage in enumerate(ranked):
                passage.relevance = scores.get(position, 0.0)
            ranked = sorted(ranked, key=lambda p: (-(p.relevance or 0.0), -p.score, p.document_id, p.chunk_index))
            reranked = True

    hints_applied = 0
    feedback = getattr(store, "feedback_hints", None)
    if feedback is not None:
        try:
            hints = feedback(property_id, list(map(float, vectors[0])), config.hint_similarity)
        except Exception:
            hints = {}
        if hints:
            known = {p.chunk_id for p in ranked}
            missing = [c for c, net in hints.items() if net > 0 and c not in known]
            extra = {p.chunk_id: p for p in store.chunks_by_id(property_id, missing)} if missing else {}
            ranked, hints_applied = apply_hints(ranked, hints, config, reranked, extra)

    strength, reasons = judge(ranked, profile, config, reranked)
    best_similarity = max((p.similarity for p in ranked[:3]), default=0.0)
    best_relevance = max((p.relevance or 0.0 for p in ranked[:3]), default=0.0) if reranked else None
    if strength == "none":
        return Retrieval([], "none", best_similarity, queries, reasons, ranked=[], best_relevance=best_relevance,
                         vector=list(map(float, vectors[0])), hints_applied=hints_applied)
    chosen = _limit_per_document(ranked, config.top_k, config.max_per_document)
    passages = _with_neighbors(store, property_id, list(chosen), config.neighbors)
    passages.sort(key=lambda p: (p.document_id, p.chunk_index))
    return Retrieval(passages, strength, best_similarity, queries, reasons, ranked=chosen, best_relevance=best_relevance,
                     vector=list(map(float, vectors[0])), hints_applied=hints_applied)


def passages_for_prompt(passages: Sequence[Passage]) -> list[dict[str, Any]]:
    """Passages as the agent prompt sees them (same keys as the document passages it
    already cites): the file name to cite, the first page, the section and the text."""
    return [{"fonte": p.document_name or "documento", "pagina": p.page_start, "sezione": p.heading,
             "testo": p.text} for p in passages]
