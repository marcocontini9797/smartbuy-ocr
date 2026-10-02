from __future__ import annotations

from typing import Any

from document_engine.document_identity import adapt_extracted_fields, resolve_document_identity
from document_engine.document_similarity import compare_documents
from document_engine.fascicolo_builder import build_fascicolo_action


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _similarity_document_from_payload(
    payload: dict[str, Any],
    *,
    document_id: str | None,
    filename: str | None,
    sha256: str | None,
) -> dict[str, Any]:
    fields = adapt_extracted_fields(_dict(payload.get("extracted_fields")))
    payload_metadata = _dict(payload.get("metadata"))
    field_metadata = _dict(fields.get("metadata"))

    metadata = {}
    metadata.update(fields)
    metadata.update(field_metadata)
    metadata.update(payload_metadata)

    return {
        "document_id": document_id,
        "file_name": filename,
        "sha256": sha256,
        "document_type": payload.get("document_type"),
        "document_series_id": _first_value(
            payload.get("document_series_id"),
            fields.get("document_series_id"),
            payload_metadata.get("document_series_id"),
            field_metadata.get("document_series_id"),
        ),
        "document_date": _first_value(
            payload.get("document_date"),
            fields.get("document_date"),
            fields.get("issue_date"),
            fields.get("data_emissione"),
            payload_metadata.get("document_date"),
            field_metadata.get("document_date"),
        ),
        "ocr_text": _first_value(
            payload.get("ocr_text"),
            payload.get("text"),
            payload.get("raw_text"),
        ) or "",
        "metadata": metadata,
        "extracted_fields": fields,
    }


def _similarity_document_from_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    fields = adapt_extracted_fields(_dict(row.get("extracted_fields")))
    metadata = _dict(row.get("metadata"))
    field_metadata = _dict(fields.get("metadata"))

    merged_metadata = {}
    merged_metadata.update(fields)
    merged_metadata.update(field_metadata)
    merged_metadata.update(metadata)

    return {
        "document_id": str(
            row.get("id")
            or row.get("document_id")
            or ""
        ),
        "file_name": (
            row.get("file_name")
            or row.get("document_name")
        ),
        "sha256": (
            row.get("content_sha256")
            or row.get("sha256")
        ),
        "document_type": row.get("document_type"),
        "document_series_id": _first_value(
            row.get("document_series_id"),
            fields.get("document_series_id"),
            metadata.get("document_series_id"),
            field_metadata.get("document_series_id"),
        ),
        "document_date": _first_value(
            row.get("document_date"),
            fields.get("document_date"),
            fields.get("issue_date"),
            fields.get("data_emissione"),
            metadata.get("document_date"),
            field_metadata.get("document_date"),
        ),
        "ocr_text": _first_value(
            row.get("ocr_text"),
            row.get("text"),
            row.get("raw_text"),
        ) or "",
        "metadata": merged_metadata,
        "extracted_fields": fields,
    }


def build_fascicolo_comparisons(
    payload: dict[str, Any],
    *,
    new_document_id: str | None,
    filename: str | None,
    sha256: str | None,
    existing_documents: list[dict[str, Any]],
    organization: dict[str, Any] | None = None,
    expected_units: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Confronta un nuovo documento con tutti i documenti
    già presenti nel fascicolo.

    Convenzione del confronto:

        existing_document -> A
        new_document      -> B

    In questo modo, quando il similarity engine restituisce:

        version["newer"] == "b"

    significa che il documento appena caricato è la versione
    più recente rispetto a quello già presente.

    Ogni confronto riporta anche "identity_resolution": che cosa significa
    la differenza (versione più recente, unità accessoria, documento di
    un'altra unità...). expected_units, se noto, sono i riferimenti
    catastali (comune, foglio, particella, subalterno) dell'immobile della
    pratica. Se omesso, sono quelli delle visure catastali già in pratica
    (expected_units_from_documents); passando [] il confronto con l'unità
    attesa è disattivato e un'unità diversa resta "expectation_unknown".

    Non modifica il database e non esegue merge automatici.
    """

    new_document = _similarity_document_from_payload(
        payload,
        document_id=new_document_id,
        filename=filename,
        sha256=sha256,
    )

    if expected_units is None:
        expected_units = expected_units_from_documents(existing_documents)

    comparisons: list[dict[str, Any]] = []

    for row in existing_documents:
        existing_document = _similarity_document_from_row(row)

        if not existing_document["document_id"]:
            continue

        # IMPORTANTE:
        # A = documento già presente
        # B = nuovo documento
        #
        # Questo mantiene coerente il campo:
        # version["newer"] == "b"
        # con l'azione "new_version" del Fascicolo Builder.
        similarity_result = compare_documents(
            existing_document,
            new_document,
        )

        identity_resolution = resolve_document_identity(
            similarity_result,
            existing_document,
            new_document,
            expected_units=expected_units,
        )

        action_result = build_fascicolo_action(
            new_document,
            existing_document=existing_document,
            similarity_result=similarity_result,
            organization=organization,
            identity_resolution=identity_resolution,
        )

        comparisons.append(
            {
                "existing_document_id": (
                    existing_document["document_id"]
                ),
                "new_document_id": new_document_id,
                "similarity": similarity_result,
                "identity_resolution": identity_resolution,
                "action": action_result,
            }
        )

    return comparisons

_IDENTITY_TYPES = {"visura_catastale", "visura"}


def expected_units_from_documents(
    existing_documents: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Cadastral units the fascicolo already attests: those of its visure
    catastali. None if there is no visura, or if any visura has incomplete
    references (a partial identity is not an expectation)."""
    units: list[dict[str, Any]] = []
    for row in existing_documents:
        kind = str(row.get("document_type") or "").strip().casefold()
        if kind not in _IDENTITY_TYPES:
            continue
        fields = adapt_extracted_fields(_dict(row.get("extracted_fields")))
        records = fields.get("riferimenti_catastali")
        if not isinstance(records, list) or not records:
            return None
        units.extend(r for r in records if isinstance(r, dict))
    return units or None


def summarize_comparisons(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    """Compact view for API responses: what to do with the new document
    and why, one line per compared document, without the full evidence."""
    items = []
    for entry in comparisons:
        action = entry.get("action") or {}
        identity = entry.get("identity_resolution") or {}
        items.append(
            {
                "existing_document_id": entry.get("existing_document_id"),
                "action": action.get("action"),
                "requires_review": bool(action.get("requires_review")),
                "reason": action.get("reason"),
                "identity_verdict": identity.get("verdict"),
                "lineage": identity.get("lineage"),
                "open_conflicts": identity.get("open_conflicts") or [],
                "automatic_merge_allowed": False,
            }
        )
    return {
        "compared_with": len(items),
        "needs_review": any(item["requires_review"] for item in items),
        "items": items,
    }
