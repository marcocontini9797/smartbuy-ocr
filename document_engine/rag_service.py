"""The two entry points the application uses for document-text retrieval: index a document
when it is uploaded, and fetch the passages that answer an agent's question.

Everything here is best effort and fails soft: without an OpenAI key, with the migration not
applied, or on any provider error the agent simply falls back to the extracted facts and
evidence it always had.
"""

from __future__ import annotations

import os
from typing import Any

EMBEDDING_DIMENSIONS = 1536


def _embed(texts: list[str]):
    from llm_client import EMBEDDING_MODEL, embed_texts
    return embed_texts(texts, model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS)


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


def retrieve_passages(client, property_id: int, question: str) -> dict[str, Any]:
    """{"passages": [...], "strength": "strong|weak|none"} — empty when retrieval is unavailable."""
    if not os.environ.get("OPENAI_API_KEY"):
        return {"passages": [], "strength": "unavailable"}
    try:
        from document_engine.rag_llm import expand_question, rerank_passages
        from document_engine.rag_search import passages_for_prompt, retrieve
        from document_engine.rag_store import SupabaseChunkStore
        result = retrieve(SupabaseChunkStore(client), _embed, property_id, question,
                          expand=expand_question, rerank=rerank_passages)
        return {"passages": passages_for_prompt(result.passages), "strength": result.strength}
    except Exception:
        return {"passages": [], "strength": "unavailable"}
