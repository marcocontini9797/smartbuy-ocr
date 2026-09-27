from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from smartbuy.profile import (
    FactProvenance,
    FactStatus,
    PropertyFact,
    PropertyIntelligenceProfile,
    SourceType,
)


class ReconciliationOutcome(str, Enum):
    consistent = "consistent"
    conflict = "conflict"
    missing = "missing"
    insufficient_evidence = "insufficient_evidence"


class FactVerificationResult(BaseModel):
    field: str
    current_value: Any | None
    current_status: FactStatus
    outcome: ReconciliationOutcome
    observations_used: int = Field(default=0, ge=0)
    discrepancy_notes: list[str] = Field(default_factory=list)
    notes: str | None = None


class ValidationReport(BaseModel):
    property_id: str
    verified_at: str
    facts: dict[str, FactVerificationResult] = Field(default_factory=dict)
    discrepancies: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    notes: str | None = None


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class CrossVerificationFinding(BaseModel):
    field: str
    label: str
    outcome: ReconciliationOutcome
    competing_sources: list[tuple[SourceType, Any]] = Field(default_factory=list)
    note: str | None = None
    important: bool = False


VERIFICATION_FIELD_META: dict[str, dict[str, Any]] = {
    "surface_m2": {
        "canonical_field": "surface_m2",
        "label": "property surface area (m2)",
        "important": True,
        "cross_reference_fields": ["surface_m2"],
    },
    "rooms": {
        "canonical_field": "rooms",
        "label": "number of rooms",
        "important": True,
        "cross_reference_fields": ["rooms"],
    },
    "price": {
        "canonical_field": "price",
        "label": "asking price",
        "important": True,
        "cross_reference_fields": ["price"],
    },
    "energy_class": {
        "canonical_field": "energy_class",
        "label": "energy class",
        "important": True,
        "cross_reference_fields": ["energy_class"],
    },
}


VALIDATION_VERIFICATION_LEVELS = {
    "not_applicable": 0,
    "weak": 1,
    "listing_bound": 2,
    "partially_verified": 3,
    "confirmed": 4,
}

VERIFICATION_LEVEL_NOT_APPLICABLE = "not_applicable"
VERIFICATION_LEVEL_WEAK = "weak"
VERIFICATION_LEVEL_CONFIRMED = "confirmed"


class ValidationEnginePOC:
    """
    Stage 6 POC validation engine.

    Current shape:
    - in-process and deterministic
    - reconciles observations already present in a PropertyIntelligenceProfile
    - does not fetch new evidence
    - uses simple, auditable rules for consistency checks

    The engine is intentionally conservative. It should not declare facts
    confirmed unless the evidence pattern is strong enough and consistent.

    The next-layer extension adds explicit cross-source discrepancy detection
    for the most important business fields so the discrepancy is not only
    visible as a raw observation conflict, but also summarized as an auditable
    cross-verification finding with the competing sources named.
    """

    def validate_profile(
        self, profile: PropertyIntelligenceProfile
    ) -> ValidationReport:
        facts: dict[str, FactVerificationResult] = {}
        discrepancies: list[str] = []
        unresolved_conflicts: list[str] = []
        cross_verification_notes: list[str] = []

        for field, fact in profile.facts.items():
            result = self._verify_fact(field, fact, profile)
            facts[field] = result
            if result.outcome == ReconciliationOutcome.conflict:
                discrepancies.append(
                    f"Field '{field}' has conflicting observations: "
                    + "; ".join(result.discrepancy_notes)
                )
                unresolved_conflicts.append(field)

        cross_results = self._cross_verify_important_fields(profile, facts)
        for item in cross_results:
            if item.outcome == ReconciliationOutcome.conflict:
                discrepancies.append(item.note or "cross-verification conflict")
                unresolved_conflicts.append(item.field)
            if item.note:
                cross_verification_notes.append(item.note)

        notes_parts = ["Stage 6 POC validation. No live sources consulted."]
        if cross_verification_notes:
            notes_parts.append(
                "Cross-verification findings: "
                + "; ".join(cross_verification_notes)
            )

        return ValidationReport(
            property_id=profile.property_id,
            verified_at=_now_iso(),
            facts=facts,
            discrepancies=discrepancies,
            unresolved_conflicts=unresolved_conflicts,
            notes=" ".join(notes_parts),
        )

    def _verify_fact(
        self, field: str, fact: PropertyFact, profile: PropertyIntelligenceProfile
    ) -> FactVerificationResult:
        observations = fact.observations
        if not observations:
            return FactVerificationResult(
                field=field,
                current_value=fact.current_value,
                current_status=fact.current_status,
                outcome=ReconciliationOutcome.missing,
                observations_used=0,
                notes="No observations recorded for this fact.",
            )

        statuses = [o.verification_status for o in observations]
        confirmed = [
            o for o in observations if o.verification_status == FactStatus.confirmed
        ]
        values = [o.value for o in observations if o.value is not None]

        if len(confirmed) >= 2 and _all_equal(values):
            return FactVerificationResult(
                field=field,
                current_value=_representative_value(values),
                current_status=FactStatus.confirmed,
                outcome=ReconciliationOutcome.consistent,
                observations_used=len(observations),
                notes="Multiple confirmed observations agree.",
            )

        if len(confirmed) == 1 and not _has_direct_conflict(observations):
            return FactVerificationResult(
                field=field,
                current_value=_representative_value(values),
                current_status=FactStatus.confirmed,
                outcome=ReconciliationOutcome.consistent,
                observations_used=len(observations),
                notes="Single confirmed observation with no conflicting evidence.",
            )

        if _has_direct_conflict(observations):
            notes = _conflict_notes(observations)
            return FactVerificationResult(
                field=field,
                current_value=fact.current_value,
                current_status=fact.current_status,
                outcome=ReconciliationOutcome.conflict,
                observations_used=len(observations),
                discrepancy_notes=notes,
                notes="Conflicting observations require reconciliation.",
            )

        if any(
            o.verification_status == FactStatus.estimated for o in observations
        ):
            return FactVerificationResult(
                field=field,
                current_value=_representative_value(values),
                current_status=FactStatus.estimated,
                outcome=ReconciliationOutcome.insufficient_evidence,
                observations_used=len(observations),
                notes="Evidence is present but not strong enough to confirm.",
            )

        return FactVerificationResult(
            field=field,
            current_value=_representative_value(values),
            current_status=fact.current_status,
            outcome=ReconciliationOutcome.insufficient_evidence,
            observations_used=len(observations),
            notes="Evidence does not yet support confirmation.",
        )

    def _cross_verify_important_fields(
        self,
        profile: PropertyIntelligenceProfile,
        facts: dict[str, FactVerificationResult],
    ) -> list[CrossVerificationFinding]:
        results: list[CrossVerificationFinding] = []

        for field, meta in VERIFICATION_FIELD_META.items():
            fact = profile.facts.get(field)
            if fact is None:
                continue

            fact_result = facts.get(field)
            if fact_result is None:
                continue

            competing: list[tuple[SourceType, Any]] = []
            for label_field in meta.get("cross_reference_fields", []):
                if label_field == field:
                    continue
                label_result = facts.get(label_field)
                if label_result is None:
                    continue
                if label_result.outcome != ReconciliationOutcome.conflict:
                    continue
                label_fact = profile.facts.get(
                    label_field, PropertyFact(field=label_field)
                )
                for observation in label_fact.observations:
                    if observation.value is not None:
                        competing.append(
                            (observation.source_type, observation.value)
                        )

            if not competing:
                continue

            values_seen = sorted(
                {f"{source.value}={value}" for source, value in competing}
            )
            results.append(
                CrossVerificationFinding(
                    field=field,
                    label=meta.get("label", field),
                    outcome=ReconciliationOutcome.conflict,
                    competing_sources=competing,
                    note=(
                        f"Field '{field}' is important and does not match the "
                        f"divergent values seen for: "
                        + ", ".join(values_seen)
                    ),
                    important=bool(meta.get("important", False)),
                )
            )

        return results


def attach_verification_to_profile(
    profile: PropertyIntelligenceProfile, report: ValidationReport
) -> PropertyIntelligenceProfile:
    """
    Stage 6 POC: apply a validation report back onto the profile.

    This updates current fact status where verification is strong enough,
    and keeps discrepancies visible on the profile.
    """
    for field, result in report.facts.items():
        fact = profile.facts.get(field)
        if fact is None:
            continue

        if (
            result.outcome == ReconciliationOutcome.consistent
            and result.observations_used >= 2
        ):
            fact.current_status = FactStatus.confirmed
        elif (
            result.outcome == ReconciliationOutcome.consistent
            and result.observations_used == 1
        ):
            fact.current_status = FactStatus.confirmed
        elif result.outcome == ReconciliationOutcome.insufficient_evidence:
            fact.current_status = FactStatus.estimated
        elif result.outcome == ReconciliationOutcome.conflict:
            fact.current_status = FactStatus.unverified

        if fact.verification_level is None:
            fact.verification_level = VERIFICATION_LEVEL_NOT_APPLICABLE

        if getattr(result, "verification_level", None):
            comparable = _verification_level_rank(result.verification_level)
            current = _verification_level_rank(
                fact.verification_level or VERIFICATION_LEVEL_WEAK
            )
            if comparable >= current:
                fact.verification_level = str(result.verification_level)

    profile.refresh_timestamps()
    return profile


def _all_equal(values: list[Any]) -> bool:
    if not values:
        return False
    first = values[0]
    return all(_equal(first, v) for v in values[1:])


def _equal(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) < 1e-6
    return a == b


def _representative_value(values: list[Any]) -> Any | None:
    for v in values:
        if v is not None:
            return v
    return None


def _has_direct_conflict(observations: list[FactProvenance]) -> bool:
    confirmed_values = [
        o.value
        for o in observations
        if o.verification_status == FactStatus.confirmed and o.value is not None
    ]
    if len(confirmed_values) < 2:
        return False
    return not _all_equal(confirmed_values)


def _conflict_notes(observations: list[FactProvenance]) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()

    for o in observations:
        key = f"{o.source_type.value}={o.value}"
        if key in seen:
            continue
        seen.add(key)
        notes.append(
            f"{o.source_type.value}: {o.value} ({o.verification_status.value})"
        )

    return notes


def _verification_level_rank(level: Any) -> int:
    key = level.value if isinstance(level, Enum) else level
    return VALIDATION_VERIFICATION_LEVELS.get(key, 0)
