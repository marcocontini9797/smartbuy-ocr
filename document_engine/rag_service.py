"""The two entry points the application uses for document-text retrieval: index a document
when it is uploaded, and fetch the passages that answer an agent's question.

Everything here is best effort and fails soft: without an OpenAI key, with the migration not
applied, or on any provider error the agent simply falls back to the extracted facts and
evidence it always had.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any

EMBEDDING_DIMENSIONS = 1536


def _embed(texts: list[str]):
    from llm_client import EMBEDDING_MODEL, embed_texts
    return embed_texts(texts, model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS)


_QUERY_CACHE: OrderedDict[str, list[float]] = OrderedDict()
_QUERY_CACHE_SIZE = 256


def _embed_queries(texts: list[str]):
    """Embeds questions through a small in-memory cache: the same question (or a rephrasing the
    expander produced before) is asked again often, and each miss is a paid provider call."""
    import numpy as np
    missing = [t for t in dict.fromkeys(texts) if t not in _QUERY_CACHE]
    if missing:
        for text, vector in zip(missing, _embed(missing)):
            _QUERY_CACHE[text] = [float(x) for x in vector]
            if len(_QUERY_CACHE) > _QUERY_CACHE_SIZE:
                _QUERY_CACHE.popitem(last=False)
    for text in texts:
        _QUERY_CACHE.move_to_end(text)
    return np.array([_QUERY_CACHE[t] for t in texts])


def backfill_missing(client, *, limit: int = 200) -> dict[str, int]:
    """Index documents that have stored OCR text but no chunks yet (uploaded before the index
    existed, or whose indexing failed). Run with a privileged client; idempotent."""
    indexed = {r["document_id"] for r in
               (client.table("document_chunks").select("document_id").execute().data or [])}
    texts = (client.table("document_text_extractions").select("document_id,raw_text").execute().data or [])
    done = skipped = 0
    for row in texts:
        if row["document_id"] in indexed or not row.get("raw_text"):
            continue
        if done + skipped >= limit:
            break
        docs = (client.table("documents").select("id,file_name,document_type,extracted_fields,superseded_by")
                .eq("id", row["document_id"]).limit(1).execute().data or [])
        if not docs or docs[0].get("superseded_by") is not None:
            skipped += 1
            continue
        doc = docs[0]
        links = (client.table("document_analyses").select("property_id")
                 .eq("document_id", doc["id"]).limit(1).execute().data or [])
        if not links:
            skipped += 1
            continue
        stored = index_uploaded_document(client, property_id=links[0]["property_id"], document=doc,
                                         ocr_text=row["raw_text"], extracted_fields=doc.get("extracted_fields"))
        done += 1 if stored else 0
        skipped += 0 if stored else 1
    return {"indexed": done, "skipped": skipped}


def index_uploaded_document(client, *, property_id: int, document: dict, ocr_text: str | None,
                            extracted_fields: dict | None = None) -> int:
    """Chunk, embed and store the document text. Returns the chunks stored (0 when skipped)."""
    if not ocr_text or not os.environ.get("OPENAI_API_KEY"):
        return 0
    try:
        from document_engine.rag_index import index_document, unit_label_from_fields
        from llm_client import EMBEDDING_MODEL
        return index_document(
            client, property_id=property_id, document_id=document["id"],
            document_type=document.get("document_type"), file_name=document.get("file_name"),
            full_text=ocr_text, embed=_embed, embedding_model=f"{EMBEDDING_MODEL}@{EMBEDDING_DIMENSIONS}",
            unit_label=unit_label_from_fields(extracted_fields))
    except Exception:
        return 0


def record_trace(client, property_id: int, question: str, result, config_version: int | None = None) -> str | None:
    """Remember what retrieval did for this question, so a later 👍/👎 can be tied to the chunks
    behind the answer. Best effort: a failure only means this answer cannot be rated."""
    try:
        row = {
            "property_id": property_id, "question": question[:1000], "strength": result.strength,
            "best_relevance": result.best_relevance, "best_similarity": result.best_similarity,
            "chunk_ids": [p.chunk_id for p in result.ranked if _is_uuid(p.chunk_id)],
            "question_embedding": result.vector, "candidates": result.candidates,
            "identifier_hit": result.identifier_hit, "config_version": config_version,
        }
        data = client.table("agent_retrieval_traces").insert(row).execute().data or []
        return str(data[0]["id"]) if data else None
    except Exception:
        return None


def _is_uuid(value: str) -> bool:
    import uuid
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def retrieve_passages(client, property_id: int, question: str) -> dict[str, Any]:
    """{"passages": [...], "strength": "strong|weak|none", "trace_id": ...} — empty when retrieval is unavailable."""
    if not os.environ.get("OPENAI_API_KEY"):
        return {"passages": [], "strength": "unavailable", "trace_id": None}
    try:
        from document_engine.rag_llm import expand_question, rerank_passages
        from document_engine.rag_search import passages_for_prompt, retrieve
        from document_engine.rag_store import SupabaseChunkStore
        from document_engine.rag_config import load_active, to_retrieval_config
        version, params = load_active(client)
        result = retrieve(SupabaseChunkStore(client), _embed_queries, property_id, question,
                          expand=expand_question, rerank=rerank_passages, config=to_retrieval_config(params))
        return {"passages": passages_for_prompt(result.passages), "strength": result.strength,
                "trace_id": record_trace(client, property_id, question, result, version)}
    except Exception:
        return {"passages": [], "strength": "unavailable", "trace_id": None}
