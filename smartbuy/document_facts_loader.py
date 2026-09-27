"""
SmartBuy Document Facts Loader

Bridge:

Supabase property_facts
        |
        ↓
Document Facts Loader
        |
        ↓
PropertyIntelligenceProfile


Gestisce:
- caricamento facts documentali
- storico osservazioni
- selezione valore migliore
- discrepanze
- mapping sezioni strutturate
"""

from __future__ import annotations


from datetime import datetime, timezone


from smartbuy.profile import (
    PropertyIntelligenceProfile,
    FactProvenance,
    FactStatus,
    SourceType,
)



# ==================================================
# IGNORED FACTS
# ==================================================

IGNORED_FACT_NAMES = {

    "tipo_documento",

    "note_incertezza",

}



# ==================================================
# STATUS PRIORITY
# ==================================================

STATUS_PRIORITY = {

    FactStatus.missing: 0,

    FactStatus.unverified: 1,

    FactStatus.estimated: 2,

    FactStatus.confirmed: 3,

}



# ==================================================
# STATUS MAPPING
# ==================================================

def _map_status(
    value: str | None
) -> FactStatus:


    value = (

        str(value).lower().strip()

        if value

        else ""

    )


    mapping = {

        "confirmed":
            FactStatus.confirmed,

        "verified":
            FactStatus.confirmed,

        "estimated":
            FactStatus.estimated,

        "pending":
            FactStatus.unverified,

        "unverified":
            FactStatus.unverified,

        "missing":
            FactStatus.missing,

    }


    return mapping.get(

        value,

        FactStatus.unverified

    )



# ==================================================
# SOURCE MAPPING
# ==================================================

def _map_source(
    value: str | None
) -> SourceType:


    value = (

        str(value).lower().strip()

        if value

        else ""

    )


    mapping = {

        "document":
            SourceType.document,

        "listing":
            SourceType.listing,

        "cadastral":
            SourceType.cadastral,

        "catasto":
            SourceType.cadastral,

        "energy":
            SourceType.energy,

        "registry":
            SourceType.registry,

    }


    return mapping.get(

        value,

        SourceType.unknown

    )



# ==================================================
# VALUE EXTRACTION
# ==================================================

def _extract_fact_value(
    record: dict
):

    value = record.get(
        "fact_value"
    )


    if isinstance(
        value,
        dict
    ):

        return value.get(
            "value"
        )


    return value




def _extract_confidence(
    record: dict
):

    try:

        return float(

            record.get(
                "confidence_score",
                0.5
            )

        )

    except Exception:

        return 0.5




def _extract_timestamp(
    record: dict
):

    return (

        record.get(
            "updated_at"
        )

        or record.get(
            "created_at"
        )

        or datetime.now(
            timezone.utc
        ).isoformat()

    )



# ==================================================
# PROPERTY FACT → PROVENANCE
# ==================================================

def property_fact_to_provenance(
    record: dict
):

    provenance = record.get(
        "provenance",
        {}
    )


    return FactProvenance(

        field=record["fact_name"],

        value=_extract_fact_value(record),


        status=_map_status(
            record.get(
                "verification_status"
            )
        ),


        source_type=_map_source(
            record.get(
                "source_type"
            )
        ),


        source_name=str(
            record.get(
                "source_document_id"
            )
        ),


        retrieved_at=_extract_timestamp(record),


        confidence=_extract_confidence(record),


        verification_status=_map_status(
            record.get(
                "verification_status"
            )
        ),


        notes=None,


        # -------------------------------
        # Document evidence
        # -------------------------------

        document_type=provenance.get(
            "source_document"
        ),


        document_page=provenance.get(
            "source_page"
        ),


        document_storage_key=None,


        evidence_text=provenance.get(
            "source_text"
        )

    )





# ==================================================
# DEDUPLICATION
# ==================================================

def _deduplicate_observations(
    observations
):

    """
    Elimina duplicati identici.

    Mantiene:
    - stesso campo
    - stesso valore
    - stessa fonte

    Mantiene invece valori diversi
    come vere discrepanze.
    """

    unique = {}

    for obs in observations:

        key = (

            obs.field,

            str(obs.value),

            obs.source_name,

            obs.verification_status

        )


        if key not in unique:

            unique[key] = obs


    return list(
        unique.values()
    )



# ==================================================
# SELECT BEST OBSERVATION
# ==================================================

def _select_best_observation(
    observations
):

    if not observations:

        return None


    return max(

        observations,

        key=lambda x: (

            STATUS_PRIORITY.get(

                x.verification_status,

                0

            ),

            x.confidence,

            x.retrieved_at

        )

    )
# ==================================================
# BUILD FACT ENTRY
# ==================================================

def build_fact_entry(
    field: str,
    observations: list
):

    observations = _deduplicate_observations(
        observations
    )


    best = _select_best_observation(
        observations
    )


    if best is None:
        return None


    alternative_values = []


    for obs in observations:

        if obs.value != best.value:

            alternative_values.append(

                f"{field}: valore alternativo '{obs.value}'"

            )


    from smartbuy.profile import PropertyFact


    return PropertyFact(

        field=field,

        current_value=best.value,

        current_status=best.status,

        current_source=best.source_type,

        current_confidence=best.confidence,

        observations=observations,

        discrepancies=alternative_values,

        verification_level=None

    )

    observations = _deduplicate_observations(
        observations
    )


    best = _select_best_observation(
        observations
    )


    if best is None:

        return None



    alternative_values = []


    for obs in observations:

        if obs.value != best.value:

            alternative_values.append(

                f"{field}: valore alternativo '{obs.value}'"

            )



    return {

        "field":
            field,


        "current_value":
            best.value,


        "current_status":
            best.status.value,


        "current_source":
            best.source_type.value,


        "current_confidence":
            best.confidence,


        "observations":
            [

                obs.model_dump()

                for obs in observations

            ],


        "discrepancies":
            alternative_values,


        "verification_level":
            None

    }




# ==================================================
# LOAD FACTS
# ==================================================

def load_document_facts_into_profile(
    profile: PropertyIntelligenceProfile,
    facts: list[dict]
):


    grouped = {}



    for fact in facts:


        name = fact.get(
            "fact_name"
        )


        if not name:

            continue



        if name in IGNORED_FACT_NAMES:

            continue



        provenance = property_fact_to_provenance(
            fact
        )


        grouped.setdefault(

            name,

            []

        ).append(

            provenance

        )



    profile.facts = {}



    for field, observations in grouped.items():


        entry = build_fact_entry(

            field,

            observations

        )


        if entry:

            profile.facts[field] = entry


    # ----------------------------------------------
    # Structured profile mappings
    # ----------------------------------------------

    _map_identity(profile)

    _map_cadastral(profile)

    _map_energy(profile)

    _map_ownership(profile)


    profile.updated_at = datetime.now(
        timezone.utc
    ).isoformat()


    return profile
# ==================================================
# STRUCTURED MAPPINGS
# ==================================================

def _map_cadastral(profile):

    riferimento = profile.facts.get(
        "riferimento"
    )

    if not riferimento:
        return

    value = riferimento.current_value

    if not isinstance(value, dict):
        return

    from smartbuy.profile import CadastralRecordFact

    if profile.cadastral is None:
        profile.cadastral = CadastralRecordFact()

    profile.cadastral.foglio = value.get(
        "foglio"
    )

    profile.cadastral.particella = value.get(
        "particella"
    )

    profile.cadastral.subalterno = value.get(
        "subalterno"
    )

    profile.cadastral.category = value.get(
        "categoria"
    )

    profile.cadastral.clas = value.get(
        "classe"
    )

    profile.cadastral.rendita_catastale = value.get(
        "rendita_catastale_eur"
    )


def _map_energy(profile):

    from smartbuy.profile import EnergyCertificateFact


    energy = profile.facts.get(
        "energy_class"
    )


    epgl = profile.facts.get(
        "epgl"
    )


    if not energy and not epgl:
        return


    if profile.energy_certificate is None:
        profile.energy_certificate = EnergyCertificateFact()



    if energy:

        profile.energy_certificate.energy_class = (
            energy.current_value
        )


        profile.energy_certificate.confidence = (
            energy.current_confidence
        )


        profile.energy_certificate.verification_status = (
            energy.current_status.value
        )


        if energy.observations:

            profile.energy_certificate.source_document_id = (
                energy.observations[0].source_name
            )



    if epgl:

        profile.energy_certificate.epgl = (
            epgl.current_value
        )


def _map_ownership(profile):

    owners = profile.facts.get(
        "intestatari"
    )

    if not owners:
        return

    value = owners.current_value

    if not value:
        return

    from smartbuy.profile import OwnershipEncumbranceFact

    if profile.ownership_encumbrance is None:
        profile.ownership_encumbrance = OwnershipEncumbranceFact()

    if isinstance(value, list):
        profile.ownership_encumbrance.owner = value[0]

    else:
        profile.ownership_encumbrance.owner = value

def _map_identity(profile):
    """
    Costruisce l'identità dell'immobile
    usando i facts documentali disponibili.
    """

    identity = {}


    # ----------------------------------------------
    # Recupero riferimento catastale
    # ----------------------------------------------

    riferimento = profile.facts.get(
        "riferimento"
    )


    if riferimento:

        value = riferimento.current_value

        if isinstance(value, dict):

            identity["address"] = value.get(
                "indirizzo"
            )

            identity["comune"] = value.get(
                "comune"
            )

            identity["cadastral_reference"] = {

                "foglio": value.get(
                    "foglio"
                ),

                "particella": value.get(
                    "particella"
                ),

                "subalterno": value.get(
                    "subalterno"
                ),

            }



    # ----------------------------------------------
    # Recupero proprietario
    # ----------------------------------------------

    intestatari = profile.facts.get(
        "intestatari"
    )


    if intestatari:

        owner = intestatari.current_value


        if owner:

            if isinstance(owner, list):

                identity["owner"] = owner[0]

            else:

                identity["owner"] = owner



    if identity:

        profile.identity = identity