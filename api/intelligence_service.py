"""Adapter from the authenticated API to the existing SmartBuy core package."""

from __future__ import annotations

import json
from hashlib import sha256
from datetime import datetime, timezone
from typing import Any


from smartbuy.document_facts_loader import load_document_facts_into_profile
from smartbuy.profile import PropertyIntelligenceProfile
from smartbuy.risk import RiskEnginePOC
from document_engine.cross_validation import HUMAN_VERIFIED, effective_facts


def _model(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


# Extraction schemas (schemas.py) name some fields differently from the names
# the profile loader maps (energy_class, epgl, riferimento, intestatari).
_PROFILE_FACT_NAMES = {
    "classe_energetica": "energy_class",
    "epgl_kwh_mq_anno": "epgl",
    "riferimenti_catastali": "riferimento",
}


def _profile_facts(facts: list[dict]) -> list[dict]:
    rows = []
    for row in effective_facts(facts):
        if row.get("verification_status") in HUMAN_VERIFIED:
            row = {**row, "verification_status": "verified"}
        name = _PROFILE_FACT_NAMES.get(row.get("fact_name"))
        if not name:
            rows.append(row)
            continue
        value = row.get("fact_value")
        if name == "riferimento" and isinstance(value, dict) and isinstance(value.get("value"), list):
            if not value["value"]:
                continue
            value = {**value, "value": value["value"][0]}
        rows.append({**row, "fact_name": name, "fact_value": value})
    return rows


# The risk engine reports "information not collected" as open risks. For the
# agent these are gaps to fill, not risks of the property: keep them apart,
# in Italian, with the document that closes each one.
_GAPS = {
    "cadastral": ("Dati catastali da raccogliere", "Carica la visura catastale"),
    "ownership": ("Proprietà e vincoli da verificare", "Carica la visura ipotecaria o l'atto di provenienza"),
    "planning": ("Conformità urbanistica da valutare", "Carica titoli edilizi e certificato di agibilità"),
    "energy": ("Dati energetici da raccogliere", "Carica l'APE"),
    "condo": ("Dati condominiali da raccogliere", "Carica regolamento, ultimi verbali e spese condominiali"),
    "location-risk": ("Rischi ambientali da valutare", "Verifica rischio idrogeologico e sismico della zona"),
    "cost": ("Costi e spese da raccogliere", "Raccogli spese condominiali, imposte e costi ricorrenti"),
    "cadastral-identifiers": ("Identificativi catastali mancanti", "Carica la visura catastale con foglio, particella e subalterno"),
    "cadastral-plan": ("Planimetria catastale da recuperare", "Carica la planimetria catastale"),
    "ownership-status": ("Titolarità da verificare", "Carica l'atto di provenienza"),
    "encumbrances": ("Ipoteche e vincoli da verificare", "Carica la visura ipotecaria"),
    "agibilità/abitabilità": ("Agibilità da verificare", "Carica il certificato di agibilità/abitabilità"),
    "ape-certificate": ("APE da recuperare", "Carica l'APE"),
    "condominium-regulation": ("Regolamento condominiale da recuperare", "Carica il regolamento di condominio"),
    "environmental-constraints": ("Vincoli ambientali da verificare", "Verifica vincoli e rischi della zona"),
    "identity": ("Identità dell'immobile da confermare", "Carica una visura catastale per identificare l'immobile"),
    "docs": ("Documenti obbligatori mancanti", "Carica i documenti richiesti nella sezione Documenti e recupero"),
    "missing-blockers": ("Informazioni bloccanti mancanti", "Completa le informazioni indicate prima di chiudere la due diligence"),
}


# Gaps SmartBuy closes by itself: flood, landslide and seismic hazard come from
# ISPRA and Protezione Civile (territory endpoint), no document needed.
_CHECKED_FROM_PUBLIC_DATA = {"location-risk"}


def _split_gaps(risks: list[dict], property_id: str) -> tuple[list[dict], list[dict]]:
    real, gaps = [], []
    for risk in risks:
        risk_id = str(risk.get("risk_id", ""))
        key = risk_id.removeprefix(f"{property_id}-").removesuffix("-missing")
        if risk_id.endswith("-missing") or key.startswith("missing-"):
            if key in _CHECKED_FROM_PUBLIC_DATA:
                continue
            field = key.removeprefix("missing-")
            title, action = _GAPS.get(key) or (
                f"Dato da raccogliere: {field.replace('_', ' ')}",
                "Carica un documento che riporti questo dato",
            )
            gaps.append({"gap_id": risk_id, "area": key, "severity": risk.get("severity"), "title": title, "action": action})
        else:
            real.append(_italian_risk(risk, key))
    return real, gaps


def _italian_risk(risk: dict, key: str) -> dict:
    """Italian wording for the engine's real risks (conflicts, weak identity)."""
    field = None
    if key.startswith("conflict-"):
        field = key.removeprefix("conflict-")
        text = (f"Dati in conflitto: {field}", f"Le fonti riportano valori diversi per '{field}'.", "Verificare le fonti e confermare il valore corretto")
    elif key.startswith("cadastral-") and key.endswith("-conflict"):
        field = key.removeprefix("cadastral-").removesuffix("-conflict")
        text = (f"Catasto non coerente: {field}", f"Il dato catastale '{field}' non coincide con le altre fonti.", "Confrontare visura, atto e scheda immobile")
    elif key == "identity-weak":
        text = ("Identità dell'immobile incerta", "Gli elementi disponibili non bastano a identificare l'immobile con certezza.", "Confermare foglio, particella e subalterno")
    else:
        return risk
    title, description, action = text
    return {**risk, "title": title, "description": description, "recommended_action": action}


def _italian_summary(documents_analyzed: int, real_risks: list[dict], gaps: list[dict]) -> str:
    if not documents_analyzed:
        return ""
    high = sum(1 for risk in real_risks if risk.get("severity") in {"critical", "high"})
    parts = [f"{documents_analyzed} document{'o analizzato' if documents_analyzed == 1 else 'i analizzati'}."]
    parts.append(f"{len(real_risks)} rischi aperti" + (f", di cui {high} importanti." if high else "."))
    if gaps:
        parts.append("Da raccogliere: " + "; ".join(gap["title"].lower() for gap in gaps) + ".")
    return " ".join(parts)


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
    profile = load_document_facts_into_profile(profile, _profile_facts(facts))
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
        row_status = row.get("verification_status")
        source_document = document_by_id.get(str(row.get("source_document_id")), {})
        source_provenance = provenance_by_id.get(str(row.get("provenance_id")), {})
        fact_rows.append({
            "id": row.get("id"),
            "field": name,
            "value": _model(aggregate.current_value) if aggregate and row_status != "rejected" else row_value,
            # The agent's own verdict on this row wins over the aggregate status.
            "status": row_status if row_status in {"corrected", "rejected"} else (
                aggregate.current_status.value if aggregate else row_status),
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
    real_risks, gaps = _split_gaps([risk.model_dump(mode="json") for risk in report.risks], property_id)
    return {
        "property": property_record,
        "profile": profile.model_dump(mode="json"),
        "risks": real_risks,
        "gaps": gaps,
        "facts": fact_rows,
        "evidence": provenance,
        "documents": documents,
        "analyses": analyses,
        "summary": {
            "analysis_status": "completed" if analyses else "not_started",
            "confidence": round(confidence, 4),
            "readiness_level": report.readiness.level.value,
            "readiness_score": report.readiness.score,
            "open_risks": sum(1 for risk in real_risks if risk.get("status") == "open"),
            "missing_items": len(gaps),
            "documents_analyzed": completed_documents,
            "executive_summary": _italian_summary(completed_documents, real_risks, gaps),
        },
        "report": report.model_dump(mode="json"),
    }
