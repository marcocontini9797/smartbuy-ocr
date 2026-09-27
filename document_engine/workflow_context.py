"""Shared, tri-state applicability for the property's operational workflow.

Answers are agent declarations, not official compliance certificates.
Unknown never means exempt and never creates a specialist document request.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class WorkflowContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occupancy: Literal["unknown", "vacant", "leased", "owner_occupied"] = "unknown"
    intended_use: str = Field(default="", max_length=300)
    activity_documents: bool | None = None
    fire_safety: bool | None = None
    has_heating: bool | None = None
    ape_applicable: bool | None = None


def applicability(record: dict) -> dict[str, bool | None]:
    context = record.get("workflow_context") or {}
    occupancy = context.get("occupancy", "unknown")
    occupied = record.get("is_rented") if occupancy == "unknown" else occupancy == "leased"
    return {
        "occupied": occupied,
        "condominium": record.get("is_condominio", record.get("is_condominium")),
        "heating": context.get("has_heating", record.get("has_heating")),
        "activity": context.get("activity_documents"),
        "fire": context.get("fire_safety"),
        "ape": False if record.get("typology") == "box" else context.get("ape_applicable"),
    }


QUESTIONS = {
    "activity": "Verificare con il SUAP o il tecnico quali titoli servono per l’attività prevista.",
    "fire": "Verificare con un tecnico l’assoggettamento ai controlli antincendio.",
    "ape": "Verificare l’applicabilità dell’APE per questo immobile e uso.",
    "occupied": "Chiarire se esiste una locazione in corso.",
    "condominium": "Chiarire se l’immobile è in condominio.",
    "heating": "Chiarire se è presente un impianto termico.",
}


def document_condition(key: str, commercial: bool) -> str | None:
    return {
        "scia_licenza_commerciale": "activity",
        "certificato_prevenzione_incendi": "fire",
        "contratto_locazione": "occupied",
        "ape": "ape" if commercial else None,
    }.get(key)
