"""Chunk stores for document_engine.rag_search: Supabase in production, memory for tests/evaluation."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Sequence

import numpy as np

from document_engine.rag_search import _plain


class SupabaseChunkStore:
    """The persistent index (public.document_chunks) through the caller's own
    Supabase client, so row level security scopes every read to their properties."""

    def __init__(self, client: Any):
        self.client = client

    def search(self, property_id: int, embedding: Sequence[float], lexical_query: str, limit: int) -> list[dict[str, Any]]:
        response = self.client.rpc("smartbuy_search_chunks", {
            "p_property_id": property_id, "p_embedding": list(embedding),
            "p_query": lexical_query, "p_limit": limit,
        }).execute()
        return response.data or []

    def neighbors(self, property_id: int, wanted: list[tuple[int, int]]) -> list[dict[str, Any]]:
        if not wanted:
            return []
        documents = sorted({document_id for document_id, _ in wanted})
        rows = (self.client.table("document_chunks")
                .select("id,document_id,chunk_index,page_start,page_end,heading,content,context")
                .eq("property_id", property_id).in_("document_id", documents).execute().data) or []
        keys = set(wanted)
        return [row for row in rows if (row["document_id"], row["chunk_index"]) in keys]


# --- in-memory store -------------------------------------------------------------------------------

_SUFFIXES = sorted([
    "amente", "azione", "azioni", "mente", "iche", "ichi", "ando", "endo", "ato", "uto", "ito", "ata", "ate",
    "ati", "ano", "ono", "are", "ere", "ire", "ica", "ico", "he", "hi", "e", "i", "a", "o",
], key=len, reverse=True)
_TOKEN = re.compile(r"[a-z0-9]+")


def stem(token: str) -> str:
    """A light Italian stemmer: close enough to Postgres' Snowball for tests and evaluation."""
    if len(token) <= 4 or token.isdigit():
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _stems(text: str) -> list[str]:
    return [stem(t) for t in _TOKEN.findall(_plain(text))]


class MemoryChunkStore:
    """Same contract and ranking semantics as smartbuy_search_chunks: the nearest
    chunks by cosine similarity and the best BM25 matches of an OR query, each with its
    rank, and the cosine similarity on every returned row."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._vectors: list[np.ndarray] = []
        self._stems: list[Counter] = []

    def add(self, *, property_id: int, document_id: int, document_name: str, document_type: str, chunk_index: int,
            page_start: int, page_end: int, heading: str | None, content: str, context: str, embedding: Sequence[float]) -> None:
        self.rows.append({
            "id": f"{document_id}:{chunk_index}", "property_id": property_id, "document_id": document_id,
            "document_name": document_name, "document_type": document_type, "chunk_index": chunk_index,
            "page_start": page_start, "page_end": page_end, "heading": heading, "content": content, "context": context,
        })
        self._vectors.append(np.asarray(embedding, dtype=float))
        self._stems.append(Counter(_stems(f"{context} {content}")))

    def _scoped(self, property_id: int) -> list[int]:
        return [i for i, row in enumerate(self.rows) if row["property_id"] == property_id]

    def search(self, property_id: int, embedding: Sequence[float], lexical_query: str, limit: int) -> list[dict[str, Any]]:
        scoped = self._scoped(property_id)
        if not scoped:
            return []
        query = np.asarray(embedding, dtype=float)
        norms = np.array([np.linalg.norm(self._vectors[i]) * np.linalg.norm(query) or 1e-9 for i in scoped])
        similarity = np.array([self._vectors[i] @ query for i in scoped]) / norms
        order = np.argsort(-similarity, kind="stable")[:limit]
        sem_rank = {scoped[int(position)]: rank + 1 for rank, position in enumerate(order)}

        terms = {stem(t) for t in _TOKEN.findall(lexical_query.replace("|", " "))}
        lex_rank: dict[int, int] = {}
        if terms:
            documents = len(scoped)
            average = sum(sum(self._stems[i].values()) for i in scoped) / documents
            frequency = {t: sum(1 for i in scoped if t in self._stems[i]) for t in terms}
            scores: dict[int, float] = {}
            for i in scoped:
                length = sum(self._stems[i].values())
                score = 0.0
                for t in terms:
                    f = self._stems[i].get(t, 0)
                    if not f:
                        continue
                    idf = math.log(1 + (documents - frequency[t] + 0.5) / (frequency[t] + 0.5))
                    score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * length / average))
                if score > 0:
                    scores[i] = score
            for rank, i in enumerate(sorted(scores, key=lambda k: (-scores[k], k))[:limit]):
                lex_rank[i] = rank + 1

        result = []
        for position, i in enumerate(scoped):
            if i in sem_rank or i in lex_rank:
                result.append({**self.rows[i], "chunk_id": self.rows[i]["id"], "similarity": float(similarity[position]),
                               "sem_rank": sem_rank.get(i), "lex_rank": lex_rank.get(i)})
        return result

    def neighbors(self, property_id: int, wanted: list[tuple[int, int]]) -> list[dict[str, Any]]:
        keys = set(wanted)
        return [row for row in self.rows if row["property_id"] == property_id
                and (row["document_id"], row["chunk_index"]) in keys]
