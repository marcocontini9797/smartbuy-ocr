"""Truthful capability registry for external Italian property sources."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from document_engine.operational_services import PROVINCE_REGION


class SourceCapability(BaseModel):
    source_id: str
    name: str
    authority: str
    region_code: str | None = None
    url: str
    access: Literal["public", "captcha", "credentials", "seller_document", "professional"]
    execution: Literal["automatic", "assisted", "manual"]
    verification_level: Literal["official", "supporting", "unverified"]
    supported_inputs: list[str] = Field(default_factory=list)
    possible_outputs: list[str] = Field(default_factory=list)
    limitation: str | None = None


REGISTRY: dict[str, SourceCapability] = {
    "sace_er": SourceCapability(
        source_id="sace_er", name="Visura APE SACE Emilia-Romagna",
        authority="Regione Emilia-Romagna", region_code="ER",
        url="https://energia.regione.emilia-romagna.it/riqualificazione-edifici-e-certificazione-energetica/certificazioneenergetica/visura-ape-ricerca-attestato-di-prestazione-energetica",
        access="captcha", execution="assisted", verification_level="official",
        supported_inputs=["ape_code", "comune_catastale", "foglio", "mappale", "subalterno"],
        possible_outputs=["certificate_status", "energy_class", "cadastral_identity", "validity"],
        limitation="Public lookup may require interactive completion; never report official verification before a result is captured.",
    ),
    "cened_lombardia": SourceCapability(
        source_id="cened_lombardia", name="Visura APE CENED Lombardia",
        authority="Regione Lombardia", region_code="LOM",
        url="https://areaoperativa.cened.it/extcatasto/html/public/visuraApe.jsf",
        access="captcha", execution="assisted", verification_level="official",
        supported_inputs=["ape_code", "comune_catastale", "foglio", "particella", "subalterno"],
        possible_outputs=["certificate_status", "energy_class", "validity"],
        limitation="Valid only for properties in Lombardia.",
    ),
    "rer_geoportal": SourceCapability(
        source_id="rer_geoportal", name="Geoportale Emilia-Romagna OGC",
        authority="Regione Emilia-Romagna", region_code="ER",
        url="https://geoportale.regione.emilia-romagna.it/servizi/servizi-ogc",
        access="public", execution="automatic", verification_level="official",
        supported_inputs=["latitude", "longitude"],
        possible_outputs=["municipality_boundary", "protected_areas", "territorial_layers"],
        limitation="Layer availability and scale vary; cadastral ownership is outside this source.",
    ),
    "ade_personal": SourceCapability(
        source_id="ade_personal", name="Consultazione personale catastale",
        authority="Agenzia delle Entrate",
        url="https://www.agenziaentrate.gov.it/portale/consultazione-personale",
        access="credentials", execution="manual", verification_level="official",
        supported_inputs=["owner_authenticated_session"],
        possible_outputs=["current_visura", "historical_visura", "cadastral_map"],
        limitation="Available to the authenticated rights holder; planimetry is restricted to entitled parties or delegates.",
    ),
    "sister": SourceCapability(
        source_id="sister", name="SISTER professional services",
        authority="Agenzia delle Entrate",
        url="https://sister.agenziaentrate.gov.it/",
        access="professional", execution="manual", verification_level="official",
        supported_inputs=["professional_credentials", "cadastral_identity"],
        possible_outputs=["cadastral_visura", "mortgage_inspection", "registry_documents"],
        limitation="Requires an enabled professional or public-body account.",
    ),
    "seller_ape": SourceCapability(
        source_id="seller_ape", name="APE supplied by seller",
        authority="Seller document",
        url="", access="seller_document", execution="automatic", verification_level="supporting",
        supported_inputs=["uploaded_ape"],
        possible_outputs=["ape_code", "energy_class", "issue_date", "expiry_date"],
        limitation="Supports extraction and consistency checks; official registry confirmation remains separate.",
    ),
}


def source_plan(*, province: str | None, available_inputs: set[str] | None = None) -> dict[str, Any]:
    inputs = available_inputs or set()
    region = PROVINCE_REGION.get((province or "").upper())
    ape_id = "sace_er" if region == "ER" else "cened_lombardia" if region == "LOM" else None
    selected = [REGISTRY["seller_ape"], REGISTRY["ade_personal"], REGISTRY["sister"]]
    if ape_id:
        selected.insert(0, REGISTRY[ape_id])
    if region == "ER":
        selected.append(REGISTRY["rer_geoportal"])
    steps = []
    for source in selected:
        missing = [item for item in source.supported_inputs if item not in inputs]
        # Alternative APE search modes: code OR complete cadastral identity.
        if source.source_id in {"sace_er", "cened_lombardia"} and "ape_code" in inputs:
            missing = []
        steps.append({
            **source.model_dump(mode="json"),
            "status": "ready" if not missing else "needs_input",
            "missing_inputs": missing,
            "requires_user_action": source.execution != "automatic" or bool(missing),
        })
    return {"province": province, "region_code": region, "sources": steps}

