"""Authenticated document ingestion for the account-owned property workspace."""

from __future__ import annotations

import json
import re
import uuid
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


# Top-level extracted fields that are metadata, not facts about the property.
_NON_FACT_FIELDS = {"tipo_documento", "note_incertezza"}


def _field_value(value):
    """CampoEstratto-like dicts carry value, citation and confidence separately."""
    if isinstance(value, dict) and "valore" in value:
        return value.get("valore"), value.get("fonte"), value.get("confidence")
    return value, None, None


def persist_document_facts(client, *, property_id: int, document: dict, analysis: dict,
                           extracted_fields: dict | None, default_confidence: float | None,
                           model_name: str | None, second_reading: dict | None = None) -> int:
    """Store each extracted field as a property fact with its provenance.

    Provenance ids are generated here so each fact is linked to its own row
    without relying on the order of rows returned by a bulk insert.
    """
    provenance_rows, fact_rows = [], []
    # A contradicting second reading is stored as another fact of the same
    # document: cross-validation then reports the field as extraction_unstable.
    readings = [(name, raw, False) for name, raw in (extracted_fields or {}).items()]
    readings += [(name, raw, True) for name, raw in (second_reading or {}).items()]
    for name, raw, is_second in readings:
        value, citation, confidence = _field_value(raw)
        if name in _NON_FACT_FIELDS or value in (None, "", [], {}):
            continue
        confidence = confidence if confidence is not None else default_confidence
        if is_second:
            citation = "Seconda lettura indipendente: valore diverso dalla prima"
            confidence = round((confidence or 0.5) * 0.5, 3)
        provenance_id = str(uuid.uuid4())
        provenance_rows.append({
            "id": provenance_id, "analysis_result_id": analysis["id"], "document_id": document["id"],
            "property_id": property_id, "fact_name": name, "fact_value": {"value": value},
            "source_type": "document", "source_document": document.get("file_name"), "source_text": citation,
            "extraction_method": "llm_second_reading" if is_second else "llm_structured_extraction_verified",
            "model_name": model_name,
            "confidence_score": confidence,
        })
        fact_rows.append({
            "property_id": property_id, "fact_name": name, "fact_value": {"value": value},
            "fact_category": document.get("document_type") or "document", "source_type": "document",
            "source_document_id": document["id"], "provenance_id": provenance_id,
            "confidence_score": confidence, "verification_status": "unverified",
        })
    if not fact_rows:
        return 0
    try:
        client.table("fact_provenance").insert(provenance_rows).execute()
        client.table("property_facts").insert(fact_rows).execute()
    except Exception as exc:
        raise HTTPException(502, "Unable to persist extracted facts") from exc
    return len(fact_rows)


DOCUMENT_BUCKET = "smartbuy-documents"


def store_original(client, *, property_id: int, document_id, filename: str, content: bytes,
                   media_type: str | None) -> str | None:
    """Keep the uploaded file in the private bucket under <user>/<property>/.

    Returns the storage path, or None if storing failed: the analysis is still
    valid, the agent just cannot reopen the original.
    """
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "documento")[-120:]
    path = f"{client.smartbuy_user_id}/{property_id}/{document_id}-{safe_name}"
    try:
        client.storage.from_(DOCUMENT_BUCKET).upload(
            path, content, {"content-type": media_type or "application/octet-stream", "upsert": "true"},
        )
        client.table("documents").update({"storage_path": path}).eq("id", document_id).execute()
    except Exception:
        return None
    return path


@router.get("/properties/{property_id}/documents/{document_id}/file")
def open_original(property_id: int, document_id: int, client=Depends(user_client)):
    """Short-lived signed link to the original file of a document of this property."""
    get_property(property_id, client)
    try:
        linked = client.table("document_analyses").select("document_id").eq("property_id", property_id)             .eq("document_id", str(document_id)).limit(1).execute().data
        rows = client.table("documents").select("storage_path,file_name").eq("id", document_id).limit(1).execute().data
    except Exception as exc:
        raise HTTPException(502, "Document service unavailable") from exc
    if not linked or not rows:
        raise HTTPException(404, "Document not found")
    if not rows[0].get("storage_path"):
        raise HTTPException(404, "The original file was not stored for this document")
    try:
        signed = client.storage.from_(DOCUMENT_BUCKET).create_signed_url(rows[0]["storage_path"], 300)
    except Exception as exc:
        raise HTTPException(502, "Unable to open the original file") from exc
    url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
    if not url:
        raise HTTPException(502, "Unable to open the original file")
    return {"url": url, "file_name": rows[0].get("file_name"), "expires_in": 300}


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
    try:
        duplicate = client.table("documents").select("id,file_name").eq("fascicolo_id", str(property_id))             .eq("content_sha256", intake.checksum_sha256).limit(1).execute().data
    except Exception as exc:
        raise HTTPException(502, "Document service unavailable") from exc
    if duplicate:
        raise HTTPException(409, f"Questo file è già stato caricato per questo immobile ({duplicate[0].get('file_name')}).")

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
    if payload.get("document_type") in (None, "", "altro") and not payload.get("extracted_fields"):
        raise HTTPException(422, "Il file non sembra un documento immobiliare riconosciuto (visura, APE, atto, planimetria…). Non è stato salvato.")
    now = datetime.now(timezone.utc).isoformat()
    document = _insert_one(client, "documents", {
        "agente_id": client.smartbuy_user_id,
        "fascicolo_id": str(property_id),
        "content_sha256": intake.checksum_sha256,
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
    original_path = store_original(
        client, property_id=property_id, document_id=document["id"], filename=file.filename or "documento",
        content=content, media_type=file.content_type,
    )
    try:
        from llm_client import MODEL as extraction_model
    except Exception:
        extraction_model = None
    facts_saved = persist_document_facts(
        client, property_id=property_id, document=document, analysis=analysis,
        extracted_fields=payload.get("extracted_fields"),
        default_confidence=payload.get("extraction_confidence"), model_name=extraction_model,
        second_reading=payload.get("extraction_disagreements"),
    )
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
        "facts_saved": facts_saved,
        "original_saved": original_path is not None,
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
