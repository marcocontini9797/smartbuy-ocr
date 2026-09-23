"""Authenticated document ingestion for the account-owned property workspace."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.property_routes import get_property
from api.session import user_client
from document_engine.ingestion import validate_file
from core.operational_models import IntakeRecord, OperationalEvidence, PipelineRun, PipelineStage, SourceMode, now_iso, stable_id


router = APIRouter(prefix="/api/v1", tags=["documents"])


def _insert_one(client, table: str, payload: dict) -> dict:
    try:
        result = client.table(table).insert(payload).execute()
        if not result.data:
            raise RuntimeError(f"No row returned by {table}")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Unable to persist {table}") from exc


def _best_effort_insert(client, table: str, payload: dict) -> None:
    """Persist observability when its migration exists without breaking intake."""
    try:
        client.table(table).upsert(payload).execute()
    except Exception:
        return


@router.post("/properties/{property_id}/documents", status_code=201)
async def analyze_property_document(
    property_id: int,
    file: UploadFile = File(...),
    client=Depends(user_client),
):
    """Analyze one document and attach its canonical records to an owned property.

    The existing Fiverr tables remain authoritative: ``documents`` stores the
    document result and ``document_analyses`` creates the property lineage.
    """
    get_property(property_id, client)
    content = await file.read()
    try:
        validate_file(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    intake = IntakeRecord.from_bytes(
        property_id=property_id, filename=file.filename or "document",
        content=content, media_type=file.content_type,
    )
    run = PipelineRun(
        property_id=property_id,
        component_versions={"intake": "1.0", "ocr": "1.0", "extraction": "1.0", "cross_validation": "1.0"},
    )
    _best_effort_insert(client, "smartbuy_analysis_runs", run.model_dump(mode="json"))
    _best_effort_insert(client, "smartbuy_run_stages", PipelineStage.completed(
        run.run_id, "document_intake", output_refs=[intake.intake_id],
        metadata={"checksum_sha256": intake.checksum_sha256, "size_bytes": intake.size_bytes},
    ).model_dump(mode="json"))

    try:
        # Lazy import keeps the workspace API available when the optional OCR
        # provider is not configured.
        from api_server import ingest_document as legacy_ingest
    except (ImportError, ValueError) as exc:
        raise HTTPException(503, "Document AI is not configured") from exc

    await file.seek(0)
    result = await legacy_ingest(
        file=file,
        fascicolo_id=str(property_id),
        agente_id=client.smartbuy_user_id,
    )
    if getattr(result, "status_code", 500) >= 400:
        try:
            detail = json.loads(result.body).get("error", "Document analysis failed")
        except Exception:
            detail = "Document analysis failed"
        raise HTTPException(result.status_code, detail)

    payload = json.loads(result.body)
    now = datetime.now(timezone.utc).isoformat()
    document = _insert_one(client, "documents", {
        "agente_id": client.smartbuy_user_id,
        "file_name": file.filename,
        "document_type": payload.get("document_type"),
        "processing_status": "completed",
        "source_type": "account_upload",
        "extracted_fields": payload.get("extracted_fields"),
        "red_flags": payload.get("red_flags") or [],
        "consistency_discrepancies": payload.get("consistency_discrepancies") or [],
        "ocr_confidence": payload.get("ocr_confidence"),
        "extraction_confidence": payload.get("extraction_confidence"),
        "confidence_score": payload.get("extraction_confidence"),
        "processed_at": payload.get("processed_at") or now,
        "processing_time_seconds": payload.get("processing_time_seconds"),
    })
    run.document_id = str(document["id"])
    run.status = "completed"
    run.completed_at = now_iso()
    analysis = _insert_one(client, "document_analyses", {
        "property_id": property_id,
        "document_id": document["id"],
        "document_name": file.filename,
        "document_type": payload.get("document_type"),
        "confidence_score": payload.get("extraction_confidence"),
        "analysis_status": "completed",
        "extracted_data": payload.get("extracted_fields"),
        "warnings": (payload.get("red_flags") or []) + (payload.get("consistency_discrepancies") or []),
        "analyzed_at": payload.get("processed_at") or now,
    })
    _best_effort_insert(client, "smartbuy_analysis_runs", run.model_dump(mode="json"))
    for name in ("ocr", "classification", "extraction"):
        _best_effort_insert(client, "smartbuy_run_stages", PipelineStage.completed(
            run.run_id, name, input_refs=[str(document["id"])], output_refs=[str(analysis["id"])],
        ).model_dump(mode="json"))
    evidence = OperationalEvidence(
        evidence_id=stable_id("evidence", property_id, document["id"], analysis["id"]),
        property_id=property_id, run_id=run.run_id, document_id=str(document["id"]),
        kind="document_analysis", source_mode=SourceMode.ACCOUNT_UPLOAD,
        source_name=file.filename or "document", confidence=payload.get("extraction_confidence"),
        payload={"analysis_id": analysis["id"], "document_type": payload.get("document_type")},
    )
    _best_effort_insert(client, "smartbuy_operational_evidence", evidence.model_dump(mode="json"))
    return {
        "status": "success",
        "property_id": property_id,
        "document": document,
        "analysis": analysis,
        "result": payload,
        "lineage": {
            "property_id": property_id,
            "document_id": document["id"],
            "analysis_id": analysis["id"],
            "intake_id": intake.intake_id,
            "run_id": run.run_id,
            "evidence_id": evidence.evidence_id,
        },
        "intake": intake.model_dump(mode="json"),
        "run": run.model_dump(mode="json"),
    }
