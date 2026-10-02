"""
Fascicolo Builder v1.

Trasforma il risultato del Document Similarity Engine in una
decisione operativa sul fascicolo immobiliare.

Il builder NON ricalcola la similarità e NON modifica documenti:
interpreta esclusivamente l'evidenza già prodotta dal similarity engine.
"""

from __future__ import annotations

from typing import Any


VERSION = "1.0"


def _organization_folder(
    organization: dict[str, Any] | None,
) -> str | None:
    if not isinstance(organization, dict):
        return None

    value = organization.get("recommended_folder")

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _organization_name(
    organization: dict[str, Any] | None,
) -> str | None:
    if not isinstance(organization, dict):
        return None

    value = organization.get("recommended_name")

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


_UNIT_REVIEW_REASONS = {
    "unit_outside_expected": (
        "Il documento riguarda un'unità catastale diversa da quelle già "
        "attestate nel fascicolo: potrebbe appartenere a un altro immobile."
    ),
    "neither_matches_expected": (
        "Né il documento nuovo né quello confrontato corrispondono "
        "all'unità attesa del fascicolo."
    ),
    "ancillary_unit_candidate": (
        "Il documento riguarda un'unità con categoria da pertinenza "
        "(box, cantina, posto auto): va confermato che appartenga "
        "allo stesso immobile."
    ),
    "overlapping_units_review": (
        "I documenti condividono solo alcune unità catastali: "
        "verificare a quale immobile si riferiscono."
    ),
    "different_units_expectation_unknown": (
        "Il documento riguarda un'unità catastale diversa e il fascicolo "
        "non ha ancora un'unità attesa con cui confrontarla."
    ),
}


def build_fascicolo_action(
    new_document: dict[str, Any],
    *,
    existing_document: dict[str, Any] | None = None,
    similarity_result: dict[str, Any] | None = None,
    organization: dict[str, Any] | None = None,
    identity_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Determina l'azione da eseguire sul fascicolo.

    Assunzione importante:
    similarity_result deve essere stato ottenuto confrontando:

        existing_document -> A
        new_document      -> B

    quindi, quando version.newer == "b", il nuovo documento è
    effettivamente la versione più recente.

    Il builder non esegue merge automatici.
    """

    if not isinstance(new_document, dict):
        raise TypeError("new_document must be a dictionary")

    if similarity_result is not None and not isinstance(
        similarity_result,
        dict,
    ):
        raise TypeError("similarity_result must be a dictionary or None")

    result = similarity_result or {}

    status = result.get("status", "insufficient_evidence")

    version_info = result.get("version")
    if not isinstance(version_info, dict):
        version_info = {}

    newer = version_info.get("newer")

    requires_review = bool(
        result.get("requires_review", False)
    )

    folder = _organization_folder(organization)
    recommended_name = _organization_name(organization)

    base = {
        "builder_version": VERSION,
        "action": "review_required",
        "requires_review": True,
        "automatic_merge_allowed": False,
        "status": status,
        "folder": folder,
        "recommended_name": recommended_name,
        "reason": None,
        "previous_document_id": None,
        "new_document_id": new_document.get("document_id"),
        "similarity_result": result,
    }

    # --------------------------------------------------
    # 1. DUPLICATO ESATTO
    # --------------------------------------------------

    if status == "duplicate":
        base.update(
            {
                "action": "duplicate",
                "requires_review": False,
                "reason": (
                    "Il documento è un duplicato esatto di "
                    "un documento già presente nel fascicolo."
                ),
            }
        )

        if existing_document:
            base["previous_document_id"] = existing_document.get(
                "document_id",
                existing_document.get("id"),
            )

        return base

    # --------------------------------------------------
    # 1b. IDENTITÀ DEL DOCUMENTO (Document Identity Resolver)
    # --------------------------------------------------
    # Dice che cosa significa una differenza: la stessa unità aggiornata,
    # un'altra unità, una pertinenza. Senza resolver vale la logica
    # basata solo sullo stato del similarity engine, qui sotto.

    identity = identity_resolution if isinstance(identity_resolution, dict) else None
    if identity:
        verdict = identity.get("verdict")
        base["identity_verdict"] = verdict
        base["lineage"] = identity.get("lineage")
        base["open_conflicts"] = list(identity.get("open_conflicts") or [])
        previous_id = None
        if existing_document:
            previous_id = existing_document.get(
                "document_id",
                existing_document.get("id"),
            )

        if verdict == "newer_version_candidate" and identity.get("newer") in {"a", "b"}:
            newer_is_new = identity["newer"] == "b"
            explicit = identity.get("lineage") == "explicit_series"
            how = (
                "la serie documentale dichiarata lo collega"
                if explicit
                else "stessa unità e stesso tipo con data di emissione "
                "diversa: la parentela tra le versioni è dedotta, non dichiarata"
            )
            base.update(
                {
                    "action": "new_version" if newer_is_new else "older_version",
                    "requires_review": True,
                    "previous_document_id": previous_id,
                    "reason": (
                        ("Possibile versione più recente" if newer_is_new
                         else "Il documento in ingresso risulta più vecchio")
                        + f" del documento già presente: {how}."
                    ),
                }
            )
            return base

        if verdict == "same_unit_conflict":
            base.update(
                {
                    "action": "review_conflict",
                    "requires_review": True,
                    "previous_document_id": previous_id,
                    "reason": (
                        "Stessa unità catastale e stessa data, ma dati "
                        "che non coincidono: verifica prima di aggiornare."
                    ),
                }
            )
            return base

        if verdict in _UNIT_REVIEW_REASONS:
            base.update(
                {
                    "action": "review_unit",
                    "requires_review": True,
                    "reason": _UNIT_REVIEW_REASONS[verdict],
                }
            )
            return base

        if verdict == "same_unit_different_document_types":
            base.update(
                {
                    "action": "add_document",
                    "requires_review": bool(identity.get("requires_review")),
                    "reason": (
                        "Stessa unità catastale, tipo di documento diverso: "
                        "si aggiunge al fascicolo come documento distinto."
                    ),
                }
            )
            return base

    # --------------------------------------------------
    # 2. NUOVA VERSIONE
    # --------------------------------------------------

    if status == "same_document_updated":

        if newer == "b":
            base.update(
                {
                    "action": "new_version",
                    "requires_review": True,
                    "reason": (
                        "Il documento è stato identificato come "
                        "possibile versione più recente dello stesso "
                        "documento."
                    ),
                }
            )

            if existing_document:
                base["previous_document_id"] = existing_document.get(
                    "document_id",
                    existing_document.get("id"),
                )

            return base

        if newer == "a":
            base.update(
                {
                    "action": "older_version",
                    "requires_review": True,
                    "reason": (
                        "Il documento in ingresso risulta più vecchio "
                        "del documento già presente nel fascicolo."
                    ),
                }
            )

            if existing_document:
                base["previous_document_id"] = existing_document.get(
                    "document_id",
                    existing_document.get("id"),
                )

            return base

        base.update(
            {
                "action": "review_required",
                "requires_review": True,
                "reason": (
                    "Il motore ha identificato una possibile relazione "
                    "di versione, ma non ha stabilito quale documento "
                    "sia il più recente."
                ),
            }
        )

        return base

    # --------------------------------------------------
    # 3. CONFLITTO
    # --------------------------------------------------

    if status == "possible_conflict":
        base.update(
            {
                "action": "review_conflict",
                "requires_review": True,
                "reason": (
                    "Sono state rilevate differenze che richiedono "
                    "una verifica prima di aggiornare il fascicolo."
                ),
            }
        )

        if existing_document:
            base["previous_document_id"] = existing_document.get(
                "document_id",
                existing_document.get("id"),
            )

        return base

    # --------------------------------------------------
    # 4. EVIDENZA INSUFFICIENTE
    # --------------------------------------------------

    if status == "insufficient_evidence":
        base.update(
            {
                "action": "review_required",
                "requires_review": True,
                "reason": (
                    "Le informazioni disponibili non sono sufficienti "
                    "per determinare automaticamente la relazione "
                    "tra i documenti."
                ),
            }
        )

        return base

    # --------------------------------------------------
    # 5. DOCUMENTO DIVERSO
    # --------------------------------------------------

    if status == "different":
        base.update(
            {
                "action": "add_document",
                "requires_review": False,
                "reason": (
                    "Il documento non risulta correlato al documento "
                    "confrontato e può essere aggiunto al fascicolo "
                    "come nuovo documento."
                ),
            }
        )

        return base

    # --------------------------------------------------
    # 6. DOCUMENTO SIMILE MA NON VERIFICATO
    # --------------------------------------------------

    if status == "similar":
        base.update(
            {
                "action": "review_similarity",
                "requires_review": True,
                "reason": (
                    "I documenti presentano similarità, ma il motore "
                    "non ha verificato una relazione di versione."
                ),
            }
        )

        if existing_document:
            base["previous_document_id"] = existing_document.get(
                "document_id",
                existing_document.get("id"),
            )

        return base

    # --------------------------------------------------
    # 7. FUORI SCOPE
    # --------------------------------------------------

    if status == "out_of_scope":
        base.update(
            {
                "action": "out_of_scope",
                "requires_review": True,
                "reason": (
                    "Il confronto non è applicabile allo scope "
                    "corrente del fascicolo."
                ),
            }
        )

        return base

    # --------------------------------------------------
    # FALLBACK SICURO
    # --------------------------------------------------

    base["reason"] = (
        "Stato del similarity engine non riconosciuto: "
        "è necessaria una revisione."
    )

    return base