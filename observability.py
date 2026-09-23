"""Versioned transport contracts. No database, backend entities or training here."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Protocol
from uuid import UUID, uuid4, uuid5

NAMESPACE = UUID("c95347e4-4562-4d08-9530-67f455bbd414")

def new_id() -> str:
    return str(uuid4())

def stable_id(kind: str, *parts: Any) -> str:
    return str(uuid5(NAMESPACE, json.dumps([kind, *parts], ensure_ascii=False, sort_keys=True)))

def digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()

class Serializable:
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)

@dataclass(kw_only=True)
class Identifiable(Serializable):
    object_id: str = field(default_factory=new_id)
    property_id: str | None = None
    document_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)
    rag_run_ids: list[str] = field(default_factory=list)
    lineage_status: str = "unbound"
    schema_version: str = "1.0"

@dataclass(kw_only=True)
class FactCandidate(Identifiable):
    """Proposal for backend validation, never a second canonical fact/profile."""
    field_path: str
    value: Any
    canonical_fact_id: str | None = None
    status: str = "unverified"

@dataclass
class Versions(Serializable):
    retrieval: str = "hybrid-rrf/1.1"
    reranker: str = "llm-rerank/1.1"
    prompt: str = "rag-qa/1.0"
    chunking: str = "structure-aware/1.0;size=800;overlap=150"
    generation_model: str | None = None
    reranker_model: str | None = None
    embedding_model: str | None = None
    lexical_model: str | None = None
    prompt_hash: str | None = None

@dataclass
class EvidenceLink(Serializable):
    """Candidate reference for the existing evidence store, NOT a second store."""
    evidence_id: str
    property_id: str
    document_id: str
    chunk_id: str
    retrieval_item_id: str
    rag_run_id: str
    quotation: str
    verification: str = "citation_exists_only"

@dataclass
class RagRun(Serializable):
    property_id: str
    query: str
    rag_run_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    versions: Versions = field(default_factory=Versions)
    items: list[Any] = field(default_factory=list)
    evidence: list[EvidenceLink] = field(default_factory=list)
    answer: str | None = None
    status: str = "started"
    error_type: str | None = None
    parameters: dict = field(default_factory=dict)
    workflow_run_id: str | None = None
    stage_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> RagRun:
        from rag import Chunk, RetrievalItem
        value = dict(data)
        value["versions"] = Versions(**value["versions"])
        value["items"] = [RetrievalItem(**{**i, "chunk": Chunk(**i["chunk"])}) for i in value["items"]]
        value["evidence"] = [EvidenceLink(**e) for e in value["evidence"]]
        return cls(**value)

    def validate_lineage(self) -> None:
        ids = set()
        for i in self.items:
            if i.retrieval_item_id in ids:
                raise ValueError("Duplicate retrieval item")
            ids.add(i.retrieval_item_id)
            if i.rag_run_id != self.rag_run_id or i.chunk.property_id != self.property_id:
                raise ValueError("Cross-property or cross-run item")
        by_id = {i.retrieval_item_id: i for i in self.items}
        for e in self.evidence:
            i = by_id.get(e.retrieval_item_id)
            if (i is None or e.rag_run_id != self.rag_run_id or e.property_id != self.property_id
                    or e.document_id != i.chunk.document_id or e.chunk_id != i.chunk.chunk_id
                    or not i.used_in_context or not i.cited_in_answer):
                raise ValueError("Broken evidence lineage")

class IntegrationAdapter(Protocol):
    """TODO(FIVERR): map canonical IDs, authorization and idempotent writes to
    existing runs/stages/evidence. A production implementation is required.
    Errors must propagate; an unsaved trace must never look persisted.
    """
    def save_rag_run(self, run: RagRun) -> None: ...

    def link_candidate(self, *, target_type: str, target_id: str,
                       property_id: str, evidence_ids: list[str],
                       expected_version: str) -> None: ...

def bind_evidence(target: Identifiable, run: RagRun, evidence_ids: list[str]) -> None:
    """Attach only explicit supporting links, never all documents in a case."""
    run.validate_lineage()
    evidence = {e.evidence_id: e for e in run.evidence}
    if not evidence_ids or any(e not in evidence for e in evidence_ids):
        raise ValueError("Explicit existing evidence required")
    if target.property_id not in (None, run.property_id):
        raise ValueError("Cross-property target")
    target.property_id = run.property_id
    target.evidence_ids = list(dict.fromkeys(target.evidence_ids + evidence_ids))
    target.document_ids = list(dict.fromkeys(target.document_ids + [evidence[e].document_id for e in evidence_ids]))
    target.rag_run_ids = list(dict.fromkeys(target.rag_run_ids + [run.rag_run_id]))
    target.lineage_status = "linked_candidate"


