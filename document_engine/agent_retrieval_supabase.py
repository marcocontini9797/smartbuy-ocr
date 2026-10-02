"""Real retrieval for the SmartBuyAgentService (document_engine/agent_service.py).

The agent subsystem shipped with only mocks for its `retrieval` dependency
(see test_agent_service.py). This reads the same tables the rest of the app
already reads (property_facts, fact_provenance, documents, document_analyses)
through the CALLER'S OWN Supabase client, so RLS scopes the answer to
properties that client's user actually owns — there is no separate,
privileged read path for the agent.

Reuses run_all_red_flags/build_fascicolo (checklist.py, red_flags.py) instead
of re-deriving risk logic, so the agent's notion of "what's wrong with this
property" never drifts from the checklist the agent themselves already sees.

build_agent_context() is the pure part (rows in, context dict out), reused by
api/share_routes.py: the shared read-only fascicolo already fetches these same
rows through its own SECURITY DEFINER path (an anonymous visitor has no
auth.uid() for RLS), so it builds the identical context from that data instead
of going through SupabaseAgentRetrieval, which assumes an authenticated client.
"""

from __future__ import annotations

from typing import Any

from document_engine.checklist import build_fascicolo
from document_engine.superseded import drop_superseded
from red_flags import run_all_red_flags

_SEVERITY_TO_RISK = {"critica": "high", "alta": "high", "media": "medium", "bassa": "low"}


def _unwrap(value):
    return value["value"] if isinstance(value, dict) and set(value) == {"value"} else value


def build_agent_context(*, property_id: int, question: str, facts: list[dict], documents: list[dict],
                        provenance: list[dict]) -> dict[str, Any]:
    documents, facts = drop_superseded(documents, facts)
    provenance_by_id = {str(row["id"]): row for row in provenance}
    document_by_id = {str(row["id"]): row for row in documents}

    fact_rows = [{"field": f.get("fact_name"), "value": _unwrap(f.get("fact_value"))} for f in facts if f.get("fact_name")]

    flags = run_all_red_flags(build_fascicolo(documents, facts))
    issue_rows = [{"title": flag.titolo, "severity": flag.gravita} for flag in flags]
    risk_level = _SEVERITY_TO_RISK.get(flags[0].gravita) if flags else "low"

    evidence_rows: list[dict[str, Any]] = []
    for fact in facts:
        prov = provenance_by_id.get(str(fact.get("provenance_id")))
        if not prov or not prov.get("source_text"):
            continue
        document = document_by_id.get(str(prov.get("document_id")), {})
        evidence_rows.append({
            "id": str(fact.get("id") or len(evidence_rows)),
            "document_id": prov.get("document_id"),
            "document": prov.get("source_document") or document.get("file_name") or "documento",
            "page": prov.get("source_page"),
            "text": prov.get("source_text"),
            "confidence": fact.get("confidence_score"),
        })

    seen_sources: set[tuple[Any, Any]] = set()
    sources: list[dict[str, Any]] = []
    for e in evidence_rows:
        key = (e["document"], e.get("page"))
        if key in seen_sources:
            continue
        seen_sources.add(key)
        sources.append({"document": e["document"], "page": e.get("page")})
    sources = sources[:8]

    return {
        "property_id": property_id,
        "query": question,
        "facts": fact_rows,
        "issues": issue_rows,
        "evidence": evidence_rows,
        "sources": sources,
        "risk_level": risk_level,
    }


class SupabaseAgentRetrieval:
    def __init__(self, client):
        self.client = client

    def _rows(self, table: str, property_id: int) -> list[dict]:
        try:
            return self.client.table(table).select("*").eq("property_id", property_id).execute().data or []
        except Exception:
            return []

    def retrieve(self, property_id: int, question: str) -> dict[str, Any]:
        facts = self._rows("property_facts", property_id)
        analyses = self._rows("document_analyses", property_id)
        document_ids = list({row["document_id"] for row in analyses if row.get("document_id") is not None})
        documents: list[dict] = []
        if document_ids:
            try:
                documents = self.client.table("documents").select("*").in_("id", document_ids).execute().data or []
            except Exception:
                documents = []
        provenance_ids = list({row["provenance_id"] for row in facts if row.get("provenance_id") is not None})
        provenance: list[dict] = []
        if provenance_ids:
            try:
                provenance = self.client.table("fact_provenance").select("*").in_("id", provenance_ids).execute().data or []
            except Exception:
                provenance = []
        context = build_agent_context(property_id=property_id, question=question, facts=facts,
                                      documents=documents, provenance=provenance)
        from document_engine.rag_service import retrieve_passages
        found = retrieve_passages(self.client, property_id, question)
        context["passages"] = found["passages"]
        context["retrieval_strength"] = found["strength"]
        return context
