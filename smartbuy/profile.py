from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FactStatus(str, Enum):
    confirmed = "confirmed"
    estimated = "estimated"
    missing = "missing"
    unverified = "unverified"


class SourceType(str, Enum):
    listing = "listing"
    cadastral = "cadastral"
    comune = "comune"
    registry = "registry"
    energy = "energy"
    gis = "gis"
    document = "document"
    seller = "seller"
    administrator = "administrator"
    user = "user"
    unknown = "unknown"


class FactProvenance(BaseModel):
    """
    Evidence attached to a single property fact.

    SmartBuy should never store only a bare value like `surface = 95`.
    Every fact should carry where it came from, when it was retrieved,
    how reliable it is, and what verification state it is in.
    """

    field: str
    value: Any
    status: FactStatus = FactStatus.unverified
    source_type: SourceType = SourceType.unknown
    source_name: str | None = None
    retrieved_at: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verification_status: FactStatus = FactStatus.unverified
    notes: str | None = None
    document_type: str | None = None
    document_page: int | None = None
    document_storage_key: str | None = None
    evidence_text: str | None = None


class PropertyFact(BaseModel):
    """
    Current aggregate view of a property fact.

    This is the "latest understood state" of a field, not the only
    historical observation. Earlier observations should still be preserved.
    """

    field: str
    current_value: Any | None = None
    current_status: FactStatus = FactStatus.unverified
    current_source: SourceType = SourceType.unknown
    current_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    observations: list[FactProvenance] = Field(default_factory=list)
    discrepancies: list[str] = Field(default_factory=list)
    verification_level: str | None = None


class DocumentRefStatus(str, Enum):
    missing = "missing"
    requested = "requested"
    received = "received"
    processing = "processing"
    verified = "verified"
    rejected = "rejected"
    failed = "failed"


class DocumentRequirement(BaseModel):
    document_type: str
    status: DocumentRefStatus = DocumentRefStatus.missing
    importance: str = "medium"
    recommended_action: str | None = None
    responsible_party: str | None = None
    notes: str | None = None


class CadastralRecordFact(BaseModel):
    """
    Cadastral side of the property.

    This is the Italian catasto side: identifiers, category/class, rendita,
    planimetria reference, and related cadastral record pointers.
    """

    foglio: str | None = None
    particella: str | None = None
    subalterno: str | None = None
    category: str | None = None
    clas: str | None = None
    rendita_catastale: float | None = None
    planimetria_reference: str | None = None
    ownership_note: str | None = None
    notes: str | None = None


class OwnershipEncumbranceFact(BaseModel):
    """
    Ownership and encumbrance information.

    This covers who legally owns the property and whether there are
    mortgages, liens, judicial registrations, seizures, or other
    encumbrances where legally accessible.
    """

    owner: str | None = None
    owner_type: str | None = None
    has_mortgage: bool | None = None
    has_lien: bool | None = None
    has_seizure: bool | None = None
    encumbrance_note: str | None = None
    notes: str | None = None


class PlanningComplianceFact(BaseModel):
    """
    Urban-planning / building compliance.

    This should eventually include permits/concessions, later modifications,
    sanatoria/condono where relevant, agibilità/abitabilità evidence, and
    the correspondence between the actual property and authorized plans.
    """

    has_built_permit: bool | None = None
    agibilita_status: str | None = None
    abitabilita_status: str | None = None
    planimetric_consistency: str | None = None
    compliance_note: str | None = None
    notes: str | None = None


class EnergyCertificateFact(BaseModel):
    """
    Energy information from the APE.

    This is the Attestato di Prestazione Energetica side:
    energy class, EPgl, certificate details, source evidence,
    and verification information.
    """

    certificate_id: str | None = None

    energy_class: str | None = None

    epgl: float | None = None

    emission_class: str | None = None

    issue_date: str | None = None

    valid_note: str | None = None

    source_document_id: str | None = None

    confidence: float | None = None

    verification_status: str | None = None

    notes: str | None = None

class CondominiumFact(BaseModel):
    """
    Condominium-side information.

    This covers condominium regulations, ordinary/extraordinary charges,
    unpaid amounts, planned major works, meeting minutes, and related
    condominium documentation.
    """

    has_condo_regulation: bool | None = None
    ordinary_charges_note: str | None = None
    extraordinary_charges_note: str | None = None
    unpaid_amt_note: str | None = None
    planned_work_note: str | None = None
    notes: str | None = None


class LocationEnvironmentalFact(BaseModel):
    """
    Location and environmental risk.

    This is the geographic/regulatory risk side: flood/hydrogeological risk,
    landslide risk, seismic classification, environmental constraints,
    protected-area/landscape constraints, and other geographically relevant
    risks.
    """

    flood_risk_note: str | None = None
    landslide_risk_note: str | None = None
    seismic_class: str | None = None
    environmental_constraint_note: str | None = None
    protected_area_note: str | None = None
    notes: str | None = None


class CostFinancialFact(BaseModel):
    """
    Financial / property-cost information.

    This covers price, cadastral value/rendita, condominium costs, taxes
    where applicable, renovation implications, estimated transaction costs,
    and potentially market comparisons.
    """

    asking_price: float | None = None
    cadastral_value: float | None = None
    condominium_cost_note: str | None = None
    tax_note: str | None = None
    renovation_note: str | None = None
    transaction_cost_note: str | None = None
    market_comparison_note: str | None = None
    notes: str | None = None


class MissingInformationItem(BaseModel):
    field_or_document: str
    status: FactStatus = FactStatus.missing
    importance: str = "medium"
    required: bool = True
    recommended_action: str = "request_provider"
    responsible_party: str | None = None
    notes: str | None = None


class PropertyIntelligenceProfile(BaseModel):
    """
    Central property profile for smartBuy.

    Conceptually this is an evidence-backed due-diligence file for an Italian
    property, built from a listing and then enriched from cadastral, registry,
    planning, energy, condominium, location/environmental, and financial
    sources.

    The listing is only the entry point. The product is the verified
    information file and the risk/readiness view that comes from comparing
    sources.

    For now this is implemented as an in-memory profile model.
    Later stages should add persistence, history preservation, and
    reconciliation logic.

    Business consequences:
    - identity, cadastral, registry/ownership, planning/building, energy,
      condominium, location/environmental, and cost/financial information are
      first-class parts of the profile
    - discrepancies between sources are stored on facts, not silently merged
    - missing information and document requirements can be derived from the
      profile and from business expectations
    """

    property_id: str
    identity: dict[str, Any] | None = None
    facts: dict[str, PropertyFact] = Field(default_factory=dict)
    documents: dict[str, DocumentRequirement] = Field(default_factory=dict)
    missing_information: list[MissingInformationItem] = Field(default_factory=list)
    retrieved_sources: list[str] = Field(default_factory=list)
    updated_at: str

    cadastral: CadastralRecordFact | None = None
    ownership_encumbrance: OwnershipEncumbranceFact | None = None
    planning_compliance: PlanningComplianceFact | None = None
    energy_certificate: EnergyCertificateFact | None = None
    condominium: CondominiumFact | None = None
    location_environmental: LocationEnvironmentalFact | None = None
    cost_financial: CostFinancialFact | None = None

    def add_observation(self, provenance: FactProvenance) -> PropertyFact:
        field = provenance.field
        existing = self.facts.get(field)

        if existing is None:
            existing = PropertyFact(field=field)
            self.facts[field] = existing

        existing.observations.append(provenance)

        if provenance.verification_status == FactStatus.confirmed:
            existing.current_value = provenance.value
            existing.current_status = FactStatus.confirmed
            existing.current_source = provenance.source_type
            existing.current_confidence = provenance.confidence
        elif provenance.verification_status == FactStatus.estimated:
            existing.current_status = FactStatus.estimated
            existing.current_value = provenance.value
            existing.current_source = provenance.source_type
            existing.current_confidence = max(
                existing.current_confidence, provenance.confidence
            )
        else:
            existing.current_value = provenance.value
            existing.current_status = FactStatus.unverified
            existing.current_source = provenance.source_type
            existing.current_confidence = provenance.confidence

        return existing

    def mark_document_status(
        self,
        document_type: str,
        status: DocumentRefStatus,
        importance: str | None = None,
        recommended_action: str | None = None,
        responsible_party: str | None = None,
        notes: str | None = None,
    ) -> DocumentRequirement:
        current = self.documents.get(document_type)
        if current:
            current.status = status
            if importance:
                current.importance = importance
            if recommended_action:
                current.recommended_action = recommended_action
            if responsible_party:
                current.responsible_party = responsible_party
            if notes:
                current.notes = notes
            return current

        requirement = DocumentRequirement(
            document_type=document_type,
            status=status,
            importance=importance or "medium",
            recommended_action=recommended_action,
            responsible_party=responsible_party,
            notes=notes,
        )
        self.documents[document_type] = requirement
        return requirement

    def require_information(
        self,
        field_or_document: str,
        importance: str | None = None,
        responsible_party: str | None = None,
        notes: str | None = None,
    ) -> MissingInformationItem:
        item = MissingInformationItem(
            field_or_document=field_or_document,
            status=FactStatus.missing,
            importance=importance or "medium",
            required=True,
            recommended_action="request_provider",
            responsible_party=responsible_party,
            notes=notes,
        )
        self.missing_information.append(item)
        return item

    def refresh_timestamps(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
