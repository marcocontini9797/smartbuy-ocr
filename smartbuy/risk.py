from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from smartbuy.profile import (
    CadastralRecordFact,
    CondominiumFact,
    CostFinancialFact,
    DocumentRefStatus,
    EnergyCertificateFact,
    FactStatus,
    LocationEnvironmentalFact,
    OwnershipEncumbranceFact,
    PlanningComplianceFact,
    PropertyIntelligenceProfile,
)
from smartbuy.validation import ReconciliationOutcome, ValidationReport


class RiskSeverity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    informational = "informational"


class RiskCategory(str, Enum):
    identity = "identity"
    cadastral = "cadastral"
    document = "document"
    energy = "energy"
    factual_discrepancy = "factual_discrepancy"
    missing_information = "missing_information"
    regulatory = "regulatory"
    financial = "financial"
    unknown = "unknown"


class RiskItem(BaseModel):
    risk_id: str
    property_id: str
    category: RiskCategory
    title: str
    severity: RiskSeverity
    description: str
    evidence_summary: str | None = None
    recommended_action: str | None = None
    status: str = "open"


class ReadinessLevel(str, Enum):
    not_started = "not_started"
    incomplete = "incomplete"
    partial = "partial"
    reviewable = "reviewable"
    ready = "ready"


class DueDiligenceReadiness(BaseModel):
    property_id: str
    assessed_at: str
    level: ReadinessLevel
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    notes: str | None = None


class FinalReportSection(str, Enum):
    summary = "summary"
    identity = "identity"
    facts = "facts"
    validation = "validation"
    documents = "documents"
    missing_information = "missing_information"
    risks = "risks"
    readiness = "readiness"
    next_steps = "next_steps"


class FinalReport(BaseModel):
    property_id: str
    generated_at: str
    sections: dict[str, Any] = Field(default_factory=dict)
    readiness: DueDiligenceReadiness
    risks: list[RiskItem] = Field(default_factory=list)
    executive_summary: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskEnginePOC:
    """
    Stage 9 POC risk engine.

    Current shape:
    - deterministic and in-process
    - reads a profile, a validation report, a missing-information view,
      and a document workflow state
    - emits a small, auditable set of risks
    - produces a readiness assessment and a final report skeleton

    This POC is intentionally conservative. It should not invent risks from
    thin air; it should mainly highlight gaps, conflicts, and unverified
    areas already visible in the profile.
    """

    def assess(
        self,
        profile: PropertyIntelligenceProfile,
        *,
        validation_report: ValidationReport | None = None,
        missing_view: Any | None = None,
        document_state: Any | None = None,
    ) -> FinalReport:
        risks = self._build_risks(
            profile,
            validation_report=validation_report,
            missing_view=missing_view,
            document_state=document_state,
        )
        readiness = self._assess_readiness(
            profile,
            validation_report=validation_report,
            missing_view=missing_view,
            document_state=document_state,
            risks=risks,
        )

        sections = self._build_sections(
            profile,
            validation_report=validation_report,
            missing_view=missing_view,
            document_state=document_state,
            risks=risks,
            readiness=readiness,
        )

        executive_summary = self._executive_summary(risks, readiness)

        return FinalReport(
            property_id=profile.property_id,
            generated_at=_now_iso(),
            sections=sections,
            readiness=readiness,
            risks=risks,
            executive_summary=executive_summary,
        )

    def _build_risks(
        self,
        profile: PropertyIntelligenceProfile,
        *,
        validation_report: ValidationReport | None = None,
        missing_view: Any | None = None,
        document_state: Any | None = None,
    ) -> list[RiskItem]:
        risks: list[RiskItem] = []

        if not profile.identity:
            risks.append(
                RiskItem(
                    risk_id=f"{profile.property_id}-identity-missing",
                    property_id=profile.property_id,
                    category=RiskCategory.identity,
                    title="Property identity not established",
                    severity=RiskSeverity.critical,
                    description="No identity information is present in the profile.",
                    evidence_summary="identity section empty",
                    recommended_action="resolve property identity before further analysis",
                )
            )
        elif _identity_confidence_low(profile):
            risks.append(
                RiskItem(
                    risk_id=f"{profile.property_id}-identity-weak",
                    property_id=profile.property_id,
                    category=RiskCategory.identity,
                    title="Property identity is weak",
                    severity=RiskSeverity.high,
                    description="Identity confidence is low and/or status is still unverified.",
                    evidence_summary=_identity_evidence_summary(profile),
                    recommended_action="confirm parcel and cadastral identity",
                )
            )

        if validation_report:
            for field in validation_report.unresolved_conflicts:
                risks.append(
                    RiskItem(
                        risk_id=f"{profile.property_id}-conflict-{field}",
                        property_id=profile.property_id,
                        category=RiskCategory.factual_discrepancy,
                        title=f"Conflicting evidence for '{field}'",
                        severity=RiskSeverity.high,
                        description=f"Validated observations for '{field}' do not agree.",
                        evidence_summary="; ".join(
                            validation_report.discrepancies
                        )
                        or "see validation report",
                        recommended_action="reconcile conflicting sources",
                    )
                )

            for field in validation_report.facts:
                result = validation_report.facts[field]
                if result.outcome == ReconciliationOutcome.missing:
                    risks.append(
                        RiskItem(
                            risk_id=f"{profile.property_id}-missing-{field}",
                            property_id=profile.property_id,
                            category=RiskCategory.missing_information,
                            title=f"No evidence for '{field}'",
                            severity=RiskSeverity.medium,
                            description=f"Validation could not find evidence for '{field}'.",
                            evidence_summary="no observations in profile",
                            recommended_action="retrieve or request evidence for this field",
                        )
                    )

        if missing_view and getattr(missing_view, "summary", {}).get("has_blockers"):
            blockers = getattr(missing_view, "ranked_blockers", [])
            if blockers:
                risks.append(
                    RiskItem(
                        risk_id=f"{profile.property_id}-missing-blockers",
                        property_id=profile.property_id,
                        category=RiskCategory.missing_information,
                        title="Blocking missing information remains",
                        severity=RiskSeverity.high,
                        description="One or more missing items are currently blocking progress.",
                        evidence_summary=", ".join(
                            item.field_or_document for item in blockers
                        ),
                        recommended_action="resolve blockers before due-diligence sign-off",
                    )
                )

        if document_state:
            missing_docs = [
                r
                for r in getattr(document_state, "required_documents", [])
                if r.status == DocumentRefStatus.missing
            ]
            if missing_docs:
                risks.append(
                    RiskItem(
                        risk_id=f"{profile.property_id}-docs-missing",
                        property_id=profile.property_id,
                        category=RiskCategory.document,
                        title="Required documents still missing",
                        severity=RiskSeverity.medium,
                        description="Some required documents have not been received.",
                        evidence_summary=", ".join(
                            r.document_type for r in missing_docs
                        ),
                        recommended_action="request or locate missing documents",
                    )
                )

        self._add_business_risks(
            profile=profile,
            validation_report=validation_report,
            risks=risks,
        )

        return risks

    def _add_business_risks(
        self,
        profile: PropertyIntelligenceProfile,
        *,
        validation_report: ValidationReport | None = None,
        risks: list[RiskItem],
    ) -> None:
        property_id = profile.property_id

        cadastral = profile.cadastral
        if cadastral is None:
            risks.append(
                RiskItem(
                    risk_id=f"{property_id}-cadastral-missing",
                    property_id=property_id,
                    category=RiskCategory.cadastral,
                    title="Cadastral information not collected",
                    severity=RiskSeverity.high,
                    description="No cadastral record information is present in the profile.",
                    evidence_summary="cadastral section empty",
                    recommended_action="retrieve cadastral record and identifiers",
                )
            )
        else:
            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.cadastral,
                "cadastral identifiers",
                cadastral.foglio is None or cadastral.particella is None,
                "cadastral identifiers are missing",
                "resolve foglio/particella/subalterno",
            )
            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.cadastral,
                "cadastral plan",
                cadastral.planimetria_reference is None,
                "cadastral plan reference is missing",
                "locate planimetria catastale reference",
            )

        ownership = profile.ownership_encumbrance
        if ownership is None:
            risks.append(
                RiskItem(
                    risk_id=f"{property_id}-ownership-missing",
                    property_id=property_id,
                    category=RiskCategory.cadastral,
                    title="Ownership/encumbrance information not collected",
                    severity=RiskSeverity.high,
                    description="No ownership or encumbrance information is present in the profile.",
                    evidence_summary="ownership/encumbrance section empty",
                    recommended_action="retrieve ownership and encumbrance status",
                )
            )
        else:
            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.cadastral,
                "ownership status",
                ownership.owner is None,
                "owner is not recorded",
                "confirm legal owner",
            )
            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.cadastral,
                "encumbrances",
                ownership.has_mortgage is None and ownership.has_lien is None and ownership.has_seizure is None,
                "encumbrance status is unknown",
                "verify mortgages/liens/seizures",
            )

        planning = profile.planning_compliance
        if planning is None:
            risks.append(
                RiskItem(
                    risk_id=f"{property_id}-planning-missing",
                    property_id=property_id,
                    category=RiskCategory.regulatory,
                    title="Planning/building compliance not assessed",
                    severity=RiskSeverity.medium,
                    description="No planning/building compliance information is present in the profile.",
                    evidence_summary="planning/compliance section empty",
                    recommended_action="assess building permits and agibilità/abitabilità",
                )
            )
        else:
            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.regulatory,
                "agibilità/abitabilità",
                planning.agibilita_status is None and planning.abitabilita_status is None,
                "agibilità/abitabilità status is missing",
                "verify agibilità/abitabilità where relevant",
            )

        energy = profile.energy_certificate

        if energy is None:

            risks.append(
                RiskItem(
                    risk_id=f"{property_id}-energy-missing",
                    property_id=property_id,
                    category=RiskCategory.missing_information,
                    title="Energy information not collected",
                    severity=RiskSeverity.medium,
                    description="No energy information is present in the profile.",
                    evidence_summary="energy certificate section empty",
                    recommended_action="obtain APE energy certificate",
                )
            )

        else:

            energy_information_missing = (
                energy.energy_class is None
                and energy.epgl is None
            )


            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.energy,
                "APE certificate",
                energy_information_missing,
                "No energy class or EPgl information available",
                "obtain or verify APE energy certificate",
            )

        condominio = profile.condominium
        if condominio is None:
            risks.append(
                RiskItem(
                    risk_id=f"{property_id}-condo-missing",
                    property_id=property_id,
                    category=RiskCategory.document,
                    title="Condominium information not collected",
                    severity=RiskSeverity.medium,
                    description="No condominium information is present in the profile.",
                    evidence_summary="condominium section empty",
                    recommended_action="collect condominium documentation",
                )
            )
        else:
            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.document,
                "condominium regulation",
                condominio.has_condo_regulation is None,
                "condominium regulation status is missing",
                "collect condominium regulations",
            )

        location = profile.location_environmental
        if location is None:
            risks.append(
                RiskItem(
                    risk_id=f"{property_id}-location-risk-missing",
                    property_id=property_id,
                    category=RiskCategory.regulatory,
                    title="Location/environmental risk not assessed",
                    severity=RiskSeverity.medium,
                    description="No location/environmental risk information is present in the profile.",
                    evidence_summary="location/environmental section empty",
                    recommended_action="assess flood/landslide/seismic/constraint risks",
                )
            )
        else:
            self._add_business_risk_if_missing(
                risks,
                property_id,
                RiskCategory.regulatory,
                "environmental constraints",
                location.environmental_constraint_note is None and location.protected_area_note is None,
                "environmental/constraint note is missing",
                "assess environmental/landscape constraints",
            )

        cost_fin = profile.cost_financial
        if cost_fin is None:
            risks.append(
                RiskItem(
                    risk_id=f"{property_id}-cost-missing",
                    property_id=property_id,
                    category=RiskCategory.financial,
                    title="Financial/cost information not collected",
                    severity=RiskSeverity.low,
                    description="No financial/cost information is present in the profile.",
                    evidence_summary="cost/financial section empty",
                    recommended_action="collect cost/financial estimates",
                )
            )

        if validation_report:
            self._add_business_discrepancy_risks(profile, validation_report, risks)

    def _add_business_risk_if_missing(
        self,
        risks: list[RiskItem],
        property_id: str,
        category: RiskCategory,
        title: str,
        missing: bool,
        evidence_summary: str,
        recommended_action: str,
    ) -> None:
        if not missing:
            return
        risks.append(
            RiskItem(
                risk_id=f"{property_id}-{title.lower().replace(' ', '-')}-missing",
                property_id=property_id,
                category=category,
                title=title,
                severity=RiskSeverity.medium,
                description=f"{title} is missing or not yet recorded.",
                evidence_summary=evidence_summary,
                recommended_action=recommended_action,
            )
        )

    def _add_business_discrepancy_risks(
        self,
        profile: PropertyIntelligenceProfile,
        validation_report: ValidationReport,
        risks: list[RiskItem],
    ) -> None:
        cadastral = profile.cadastral
        if cadastral is not None and validation_report:
            for field, result in validation_report.facts.items():
                if result.outcome == ReconciliationOutcome.conflict:
                    risks.append(
                        RiskItem(
                            risk_id=f"{profile.property_id}-cadastral-{field}-conflict",
                            property_id=profile.property_id,
                            category=RiskCategory.factual_discrepancy,
                            title=f"Cadastral/source discrepancy for '{field}'",
                            severity=RiskSeverity.high,
                            description=f"Cadastral/source observations for '{field}' do not agree.",
                            evidence_summary="; ".join(
                                validation_report.discrepancies
                            )
                            or "see validation report",
                            recommended_action="reconcile cadastral and listing/source evidence",
                        )
                    )

    def _assess_readiness(
        self,
        profile: PropertyIntelligenceProfile,
        *,
        validation_report: ValidationReport | None = None,
        missing_view: Any | None = None,
        document_state: Any | None = None,
        risks: list[RiskItem] | None = None,
    ) -> DueDiligenceReadiness:
        risks = risks or []
        critical_or_high = [
            r
            for r in risks
            if r.severity in {RiskSeverity.critical, RiskSeverity.high}
        ]
        unresolved_conflicts = bool(validation_report and validation_report.unresolved_conflicts)
        missing_blockers = False
        if missing_view and getattr(missing_view, "summary", {}).get("has_blockers"):
            missing_blockers = True

        concerns: list[str] = []
        blockers: list[str] = []
        strengths: list[str] = []

        if profile.identity:
            strengths.append("property identity exists")
            if _identity_confidence_low(profile):
                concerns.append("property identity is weak")
            else:
                strengths.append("property identity looks adequate for now")

        if validation_report:
            if unresolved_conflicts:
                concerns.append("there are unresolved factual conflicts")
                blockers.append("factual conflicts must be resolved")
            else:
                strengths.append("no unresolved validation conflicts")

        if missing_blockers:
            blockers.append("missing information blockers remain")
            concerns.append("blocking missing information is still open")

        if not profile.facts:
            concerns.append("no facts have been recorded yet")
        else:
            strengths.append(f"{len(profile.facts)} fact(s) recorded")

        if document_state:
            received_docs = [
                r
                for r in getattr(document_state, "required_documents", [])
                if r.status == DocumentRefStatus.received
            ]
            if received_docs:
                strengths.append(f"{len(received_docs)} document(s) received")
            missing_docs = [
                r
                for r in getattr(document_state, "required_documents", [])
                if r.status == DocumentRefStatus.missing
            ]
            if missing_docs:
                concerns.append(f"{len(missing_docs)} document(s) still missing")

        if critical_or_high:
            blockers.extend(
                [r.title for r in critical_or_high if r.severity in {RiskSeverity.critical, RiskSeverity.high}]
            )

        if not profile.identity:
            level = ReadinessLevel.not_started
        elif critical_or_high and unresolved_conflicts:
            level = ReadinessLevel.incomplete
        elif missing_blockers or unresolved_conflicts:
            level = ReadinessLevel.partial
        elif concerns and not blockers:
            level = ReadinessLevel.reviewable
        else:
            level = ReadinessLevel.ready

        score = _readiness_score(
            level=level,
            critical_or_high=len(critical_or_high),
            unresolved_conflicts=unresolved_conflicts,
            missing_blockers=missing_blockers,
            total_missing=getattr(missing_view, "summary", {}).get("total_missing_items", 0),
        )

        notes = None
        if level in {ReadinessLevel.not_started, ReadinessLevel.incomplete}:
            notes = "This property is not ready for due-diligence sign-off yet."
        elif level == ReadinessLevel.partial:
            notes = "Progress has been made, but blockers still prevent readiness."
        elif level == ReadinessLevel.reviewable:
            notes = "The file is reviewable, but concerns should be resolved before final sign-off."

        return DueDiligenceReadiness(
            property_id=profile.property_id,
            assessed_at=_now_iso(),
            level=level,
            score=score,
            strengths=strengths,
            concerns=concerns,
            blockers=blockers,
            notes=notes,
        )

    def _build_sections(
        self,
        profile: PropertyIntelligenceProfile,
        *,
        validation_report: ValidationReport | None = None,
        missing_view: Any | None = None,
        document_state: Any | None = None,
        risks: list[RiskItem] | None = None,
        readiness: DueDiligenceReadiness | None = None,
    ) -> dict[str, Any]:
        risks = risks or []
        readiness = readiness or DueDiligenceReadiness(
            property_id=profile.property_id,
            assessed_at=_now_iso(),
            level=ReadinessLevel.not_started,
        )

        return {
            FinalReportSection.summary.value: self._summary_section(profile, readiness),
            FinalReportSection.identity.value: self._identity_section(profile),
            FinalReportSection.facts.value: self._facts_section(profile),
            FinalReportSection.validation.value: self._validation_section(validation_report),
            FinalReportSection.documents.value: self._documents_section(document_state),
            FinalReportSection.missing_information.value: self._missing_section(missing_view),
            FinalReportSection.risks.value: [r.model_dump() for r in risks],
            FinalReportSection.readiness.value: readiness.model_dump(),
            FinalReportSection.next_steps.value: self._next_steps_section(risks, readiness),
        }

    def _summary_section(
        self, profile: PropertyIntelligenceProfile, readiness: DueDiligenceReadiness
    ) -> dict[str, Any]:
        return {
            "property_id": profile.property_id,
            "readiness_level": readiness.level.value,
            "readiness_score": readiness.score,
            "notes": readiness.notes,
        }

    def _identity_section(
        self,
        profile: PropertyIntelligenceProfile
    ) -> dict[str, Any]:
        if not profile.identity:
            return {"status": "missing"}

        identity = profile.identity
        return {
            "status": identity.get("status", "identified"),
            "address": identity.get("address"),
            "municipality": identity.get("municipality") or identity.get("comune"),
            "owner": identity.get("owner"),
            "cadastral_reference": identity.get("cadastral_reference"),
            "confidence": identity.get("confidence", 0.95),
            "notes": identity.get("notes"),
        }

    def _facts_section(self, profile: PropertyIntelligenceProfile) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        for field, fact in profile.facts.items():
            facts[field] = {
                "current_value": fact.current_value,
                "current_status": fact.current_status.value,
                "current_confidence": fact.current_confidence,
                "observation_count": len(fact.observations),
            }
        return facts

    def _validation_section(self, validation_report: ValidationReport | None) -> dict[str, Any]:
        if validation_report is None:
            return {"status": "not_run"}
        return {
            "verified_at": validation_report.verified_at,
            "discrepancies": validation_report.discrepancies,
            "unresolved_conflicts": validation_report.unresolved_conflicts,
            "facts": {
                field: {
                    "outcome": result.outcome.value,
                    "current_status": result.current_status.value,
                    "observations_used": result.observations_used,
                }
                for field, result in validation_report.facts.items()
            },
        }

    def _documents_section(self, document_state: Any | None) -> dict[str, Any]:
        if document_state is None:
            return {"status": "not_run"}

        return {
            "required_document_count": len(getattr(document_state, "required_documents", [])),
            "received_count": len(
                [
                    r
                    for r in getattr(document_state, "required_documents", [])
                    if r.status == DocumentRefStatus.received
                ]
            ),
            "missing_count": len(
                [
                    r
                    for r in getattr(document_state, "required_documents", [])
                    if r.status == DocumentRefStatus.missing
                ]
            ),
            "requested_count": len(
                [
                    r
                    for r in getattr(document_state, "required_documents", [])
                    if r.status == DocumentRefStatus.requested
                ]
            ),
            "verification_count": len(getattr(document_state, "verifications", [])),
            "next_action_notes": getattr(document_state, "next_action_notes", None),
        }

    def _missing_section(self, missing_view: Any | None) -> dict[str, Any]:
        if missing_view is None:
            return {"status": "not_run"}
        return {
            "total_missing_items": getattr(missing_view, "summary", {}).get("total_missing_items", 0),
            "blocking_count": getattr(missing_view, "summary", {}).get("blocking_count", 0),
            "high_count": getattr(missing_view, "summary", {}).get("high_count", 0),
            "medium_count": getattr(missing_view, "summary", {}).get("medium_count", 0),
            "low_count": getattr(missing_view, "summary", {}).get("low_count", 0),
            "informational_count": getattr(missing_view, "summary", {}).get("informational_count", 0),
        }

    def _next_steps_section(
        self,
        risks: list[RiskItem],
        readiness: DueDiligenceReadiness,
    ) -> list[str]:
        steps: list[str] = []

        for blocker in readiness.blockers:
            steps.append(f"Resolve: {blocker}")

        critical_risks = [r for r in risks if r.severity == RiskSeverity.critical]
        high_risks = [r for r in risks if r.severity == RiskSeverity.high]

        for risk in critical_risks + high_risks:
            if risk.recommended_action:
                steps.append(f"{risk.title}: {risk.recommended_action}")

        if not steps:
            steps.append("No immediate blockers detected in this POC assessment.")

        return steps

    def _executive_summary(
        self,
        risks: list[RiskItem],
        readiness: DueDiligenceReadiness,
    ) -> str | None:
        critical = [r for r in risks if r.severity == RiskSeverity.critical]
        high = [r for r in risks if r.severity == RiskSeverity.high]

        parts = [f"Readiness: {readiness.level.value}."]

        if critical:
            parts.append(
                f"Critical risks: {len(critical)} "
                + (";" if high else ".")
            )
        if high:
            parts.append(f"High risks: {len(high)}.")

        if readiness.blockers:
            parts.append(
                "Blockers: "
                + "; ".join(readiness.blockers)
                + "."
            )

        return " ".join(parts) if parts else None


def _identity_confidence_low(profile: PropertyIntelligenceProfile) -> bool:
    identity = profile.identity or {}
    confidence = identity.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.5:
        return True
    status = identity.get("status")
    if status in {"not_verified", "needs_verification"}:
        return True
    return False


def _identity_evidence_summary(profile: PropertyIntelligenceProfile) -> str | None:
    identity = profile.identity or {}
    parts: list[str] = []
    if identity.get("municipality"):
        parts.append(f"municipality={identity['municipality']}")
    if identity.get("province_code"):
        parts.append(f"province_code={identity['province_code']}")
    if identity.get("confidence") is not None:
        parts.append(f"confidence={identity['confidence']}")
    if identity.get("status"):
        parts.append(f"status={identity['status']}")
    return "; ".join(parts) or None


def _readiness_score(
    *,
    level: ReadinessLevel,
    critical_or_high: int,
    unresolved_conflicts: bool,
    missing_blockers: bool,
    total_missing: int,
) -> float:
    if level == ReadinessLevel.ready:
        return 0.9
    if level == ReadinessLevel.reviewable:
        return 0.7
    if level == ReadinessLevel.partial:
        return 0.4
    if level == ReadinessLevel.incomplete:
        return 0.2
    return 0.05
