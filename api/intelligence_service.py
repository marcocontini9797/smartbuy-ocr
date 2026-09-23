"""Adapter from the authenticated API to the existing SmartBuy core package."""

from __future__ import annotations

import sys
import json
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from smartbuy.document_facts_loader import load_document_facts_into_profile
from smartbuy.profile import PropertyIntelligenceProfile
from smartbuy.risk import RiskEnginePOC


def _model(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def build_property_intelligence(
    *,
    property_record: dict,
    facts: list[dict],
    documents: list[dict],
    analyses: list[dict],
    provenance: list[dict],
) -> dict:
    """Build the real PropertyIntelligenceProfile and its deterministic report."""
    property_id = str(property_record["id"])
    profile = PropertyIntelligenceProfile(
        property_id=property_id,
        identity={
            "property_id": property_id,
            "status": "confirmed" if property_record.get("address") and property_record.get("city") else "unverified",
            "address": property_record.get("address"),
            "municipality": property_record.get("city"),
            "coordinates": {
                "latitude": property_record.get("latitude"),
                "longitude": property_record.get("longitude"),
            },
            "confidence": 0.95 if property_record.get("address") and property_record.get("city") else 0.5,
            "notes": "Identity loaded from the authenticated account property.",
        },
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    profile = load_document_facts_into_profile(profile, facts)
    report = RiskEnginePOC().assess(profile)

    provenance_by_id = {str(row.get("id")): row for row in provenance if row.get("id") is not None}
    document_by_id = {str(row.get("id")): row for row in documents if row.get("id") is not None}
    fact_rows = []
    for row in facts:
        name = row.get("fact_name")
        aggregate = profile.facts.get(name) if name else None
        row_value = row.get("fact_value")
        if isinstance(row_value, dict) and set(row_value) == {"value"}:
            row_value = row_value["value"]
        feedback_payload = {"field": name, "value": row_value}
        source_document = document_by_id.get(str(row.get("source_document_id")), {})
        source_provenance = provenance_by_id.get(str(row.get("provenance_id")), {})
        fact_rows.append({
            "id": row.get("id"),
            "field": name,
            "value": _model(aggregate.current_value) if aggregate else row.get("fact_value"),
            "status": aggregate.current_status.value if aggregate else row.get("verification_status"),
            "confidence": aggregate.current_confidence if aggregate else row.get("confidence_score"),
            "source_type": row.get("source_type"),
            "source_document_id": row.get("source_document_id"),
            "source_document": source_document.get("file_name"),
            "provenance": source_provenance or None,
            "discrepancies": list(aggregate.discrepancies) if aggregate else [],
            "feedback": {
                "expected_version": str(row.get("updated_at") or sha256(json.dumps(feedback_payload, sort_keys=True, default=str).encode()).hexdigest()[:16]),
                "original_payload": feedback_payload,
            },
        })

    confidence_values = [
        fact.current_confidence for fact in profile.facts.values()
        if fact.current_confidence is not None
    ]
    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    completed_documents = sum(
        1 for row in documents if str(row.get("processing_status", "")).lower() in {"completed", "processed", "analyzed"}
    )
    return {
        "property": property_record,
        "profile": profile.model_dump(mode="json"),
        "risks": [risk.model_dump(mode="json") for risk in report.risks],
        "facts": fact_rows,
        "evidence": provenance,
        "documents": documents,
        "analyses": analyses,
        "summary": {
            "analysis_status": "completed" if analyses else "not_started",
            "confidence": round(confidence, 4),
            "readiness_level": report.readiness.level.value,
            "readiness_score": report.readiness.score,
            "open_risks": sum(1 for risk in report.risks if risk.status == "open"),
            "documents_analyzed": completed_documents,
            "executive_summary": report.executive_summary,
        },
        "report": report.model_dump(mode="json"),
    }
