"""Build and persist the retrieval index of one document.

Contextual retrieval (a chunk is indexed together with a short line that situates it
in its document) without a language-model call per chunk: the context is built from
what is already known, deterministically and for free: the kind of document, its
file name, the pages, the section heading and the cadastral unit it refers to. A
chunk that says "il prezzo e' stabilito in Euro 285.000" is then findable by
"atto di compravendita" even though those words are not in it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from document_engine.rag_chunking import chunk_document

DOCUMENT_LABELS = {
    "visura_catastale": "Visura catastale", "visura_ipotecaria": "Ispezione ipotecaria",
    "ape": "Attestato di prestazione energetica (APE)", "planimetria_catastale": "Planimetria catastale",
    "atto_compravendita": "Atto di compravendita", "atto_provenienza": "Atto di provenienza",
    "atto_di_provenienza": "Atto di provenienza", "preliminare_compravendita": "Contratto preliminare di compravendita",
    "contratto_locazione": "Contratto di locazione", "regolamento_condominio": "Regolamento di condominio",
    "verbale_assemblea_condominio": "Verbale di assemblea condominiale",
    "relazione_tecnica_integrata": "Relazione tecnica integrata", "perizia_di_stima": "Perizia di stima",
    "titolo_edilizio": "Titolo edilizio", "certificato_agibilita": "Certificato di agibilità",
    "certificato_destinazione_urbanistica": "Certificato di destinazione urbanistica",
    "dichiarazione_conformita_impianti": "Dichiarazione di conformità degli impianti",
}
EMBED_BATCH = 64


@dataclass(frozen=True)
class ChunkRow:
    chunk_index: int
    page_start: int
    page_end: int
    heading: str | None
    content: str
    context: str

    @property
    def embedding_text(self) -> str:
        return f"{self.context}\n{self.content}" if self.context else self.content

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.embedding_text.encode("utf-8")).hexdigest()


def document_label(document_type: str | None) -> str:
    kind = (document_type or "").strip()
    return DOCUMENT_LABELS.get(kind, kind.replace("_", " ").capitalize() if kind else "Documento")


def build_context(*, document_type: str | None, file_name: str | None, pages: str, heading: str | None,
                  unit_label: str | None) -> str:
    parts = [f"{document_label(document_type)} «{file_name}»" if file_name else document_label(document_type),
             f"pag. {pages}"]
    if heading:
        parts.append(heading.strip())
    if unit_label:
        parts.append(unit_label)
    return " — ".join(parts)


def build_chunk_rows(*, document_type: str | None, file_name: str | None, full_text: str,
                     unit_label: str | None = None) -> list[ChunkRow]:
    rows = []
    for chunk in chunk_document(full_text):
        pages = str(chunk.page_start) if chunk.page_start == chunk.page_end else f"{chunk.page_start}-{chunk.page_end}"
        rows.append(ChunkRow(
            chunk_index=chunk.index, page_start=chunk.page_start, page_end=chunk.page_end, heading=chunk.heading,
            content=chunk.text,
            context=build_context(document_type=document_type, file_name=file_name, pages=pages,
                                  heading=chunk.heading, unit_label=unit_label),
        ))
    return rows


def unit_label_from_fields(extracted_fields: dict[str, Any] | None) -> str | None:
    """"Bologna fg 12 part 34 sub 3" from the extracted cadastral reference, if complete."""
    from document_engine.document_identity import adapt_extracted_fields

    records = adapt_extracted_fields(extracted_fields or {}).get("riferimenti_catastali")
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        return None
    record = records[0]
    parts = [str(record.get("comune") or "").strip()] + [
        f"{label} {record[key]}" for label, key in (("fg", "foglio"), ("part", "particella"), ("sub", "subalterno"))
        if record.get(key) not in (None, "")]
    return " ".join(p for p in parts if p) or None


def embed_in_batches(embed: Callable[[list[str]], np.ndarray], texts: list[str], size: int = EMBED_BATCH) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), size):
        vectors.extend(np.asarray(embed(texts[start:start + size]), dtype=float).tolist())
    return vectors


def index_document(client: Any, *, property_id: int, document_id: int, document_type: str | None, file_name: str | None,
                   full_text: str, embed: Callable[[list[str]], np.ndarray], embedding_model: str,
                   unit_label: str | None = None) -> int:
    """(Re)index one document. Idempotent: if the stored chunks already carry the same
    content hashes nothing is embedded or written. Returns the number of chunks stored."""
    rows = build_chunk_rows(document_type=document_type, file_name=file_name, full_text=full_text, unit_label=unit_label)
    existing = (client.table("document_chunks").select("chunk_index,content_hash")
                .eq("document_id", document_id).execute().data) or []
    if existing and {(r["chunk_index"], r["content_hash"]) for r in existing} == {(r.chunk_index, r.content_hash) for r in rows}:
        return len(rows)
    if existing:
        client.table("document_chunks").delete().eq("document_id", document_id).execute()
    if not rows:
        return 0
    vectors = embed_in_batches(embed, [r.embedding_text for r in rows])
    payload = [{
        "property_id": property_id, "document_id": document_id, "chunk_index": r.chunk_index,
        "page_start": r.page_start, "page_end": r.page_end, "heading": r.heading, "content": r.content,
        "context": r.context, "embedding": vector, "embedding_model": embedding_model, "content_hash": r.content_hash,
    } for r, vector in zip(rows, vectors)]
    for start in range(0, len(payload), 50):
        client.table("document_chunks").insert(payload[start:start + 50]).execute()
    return len(rows)
