"""Authenticated document ingestion for the account-owned property workspace."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.property_routes import get_property
from api.session import user_client
from document_engine.ingestion import validate_file, MAX_FILE_SIZE
from document_engine.superseded import SupersedeError, validate_supersede
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
    if isinstance(value, dict) and "value" in value:
        return value.get("value"), value.get("source_text"), value.get("confidence")
    return value, None, None


def persist_document_facts(client, *, property_id: int, document: dict, analysis: dict,
                           extracted_fields: dict | None, default_confidence: float | None = None,
                           model_name: str | None = None, second_reading: dict | None = None, unsupported_fields: set[str] | None = None) -> int:
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
        confidence = _confidence(confidence if confidence is not None else default_confidence)
        if name in (unsupported_fields or set()):
            confidence = min(confidence if confidence is not None else 0.2, 0.2)
        if is_second:
            # Keep the actual citation; the extraction_method records this reading.
            confidence = round(confidence * 0.5, 3) if confidence is not None else None
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



def _confidence(value):
    """Keep unknown confidence unknown; never promote zero to a positive score."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 <= number <= 1 else None
    except (ValueError, TypeError):
        return None


def _organization(payload, filename):
    """Optional suggestions only; requires no new Supabase columns."""
    try:
        from document_engine.document_organizer import organize_document
        from document_engine.models import DocumentClassification, DocumentType, DocumentCategory
        aliases = {"atto_provenienza": "atto_compravendita", "atto_notarile": "atto_compravendita",
                   "planimetria": "planimetria_catastale"}
        kind = DocumentType(aliases.get(payload.get("document_type"), payload.get("document_type")))
        categories = {
            "visura_catastale": "catasto", "planimetria_catastale": "catasto",
            "estratto_mappa": "catasto", "ape": "energetico",
            "atto_compravendita": "legale", "cila": "urbanistica",
            "scia": "urbanistica", "permesso_costruire": "urbanistica",
        }
        classification = DocumentClassification(
            document_type=kind, category=DocumentCategory(categories.get(kind.value, "altro")),
            confidence=_confidence(payload.get("extraction_confidence")) or 0.0,
            reason="Tipo documento restituito dalla pipeline", evidence=[],
        )
        return organize_document(classification, filename)
    except Exception:
        # Unsupported organizer types must not prevent intake.
        return None


def _save_ocr_text(client, document: dict, ocr_text: str | None) -> None:
    """Keep the OCR text so later uploads can be compared with the content of
    this document, not only with its extracted fields. Best effort: the
    analysis is already saved and valid without it."""
    if not ocr_text:
        return
    try:
        client.table("document_text_extractions").insert({
            "document_id": document["id"], "extraction_method": "vision_ocr",
            "raw_text": ocr_text, "character_count": len(ocr_text),
        }).execute()
    except Exception:
        return


def _attach_ocr_text(client, rows: list[dict], document_type) -> None:
    """Add stored OCR text to the rows of the same document type as the new
    upload: only those are compared by content, and loading every text of the
    fascicolo on each upload would be wasted work. Rows are updated in place;
    on any failure they simply stay without text."""
    kind = str(document_type or "").strip().casefold()
    same = [row for row in rows if kind and str(row.get("document_type") or "").strip().casefold() == kind]
    if not same:
        return
    try:
        texts = client.table("document_text_extractions").select("document_id,raw_text").in_(
            "document_id", [row["id"] for row in same]).execute().data or []
    except Exception:
        return
    by_id = {str(item.get("document_id")): item.get("raw_text") for item in texts}
    for row in same:
        text = by_id.get(str(row["id"]))
        if isinstance(text, str) and text:
            row["ocr_text"] = text


def _fascicolo_review(client, property_id: int, document: dict, payload: dict, filename: str, checksum: str,
                      ocr_text: str | None = None):
    """Advisory comparison of the new document with the rest of the fascicolo
    (new version? another cadastral unit? an accessory?). Nothing is merged or
    replaced. The document is already saved, so any failure here yields None
    rather than failing the upload."""
    try:
        from document_engine.fascicolo_integration import build_fascicolo_comparisons, summarize_comparisons
        from document_engine.superseded import current_documents
        rows = client.table("documents").select(
            "id,file_name,document_type,extracted_fields,content_sha256,processing_status,superseded_by"
        ).eq("fascicolo_id", str(property_id)).execute().data or []
        existing = current_documents([row for row in rows if str(row.get("id")) != str(document["id"])
                                      and row.get("processing_status") not in {"failed", "rejected"}])
        _attach_ocr_text(client, existing, payload.get("document_type"))
        return summarize_comparisons(build_fascicolo_comparisons(
            {**payload, "ocr_text": ocr_text} if ocr_text else payload,
            new_document_id=str(document["id"]), filename=filename,
            sha256=checksum, existing_documents=existing,
        ))
    except Exception:
        return None


def _unsupported_fields(payload):
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        return set()
    items = verification.get("campi_non_supportati")
    if not isinstance(items, list):
        return set()
    return {re.split(r"[.\[]", item["campo"])[0] for item in items
            if isinstance(item, dict) and isinstance(item.get("campo"), str)}


def _mark_failed(client, run):
    run.status = "failed"
    run.completed_at = now_iso()
    run.error = "Document pipeline failed; inspect canonical records before retrying"
    _best_effort_insert(client, "smartbuy_analysis_runs", run.model_dump(mode="json"))
    if run.document_id is not None:
        try:
            client.table("documents").update({"processing_status": "failed"}).eq("id", run.document_id).execute()
        except Exception:
            pass

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


class SupersedeRequest(BaseModel):
    replaced_by: int


_SUPERSEDE_COLUMNS = "id,file_name,document_type,processing_status,superseded_by"


@router.post("/properties/{property_id}/documents/{document_id}/supersede")
def supersede_document(property_id: int, document_id: int, body: SupersedeRequest, client=Depends(user_client)):
    """Mark a document as replaced by a newer version of the same kind. Nothing
    is deleted and it can be undone; the replaced version just stops counting
    in the checks."""
    get_property(property_id, client)
    try:
        rows = client.table("documents").select(_SUPERSEDE_COLUMNS).eq("fascicolo_id", str(property_id))             .in_("id", [document_id, body.replaced_by]).execute().data or []
    except Exception as exc:
        raise HTTPException(502, "Document service unavailable") from exc
    by_id = {str(row["id"]): row for row in rows}
    try:
        validate_supersede(by_id.get(str(document_id)), by_id.get(str(body.replaced_by)))
    except SupersedeError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        updated = client.table("documents").update({"superseded_by": body.replaced_by, "superseded_at": stamp})             .eq("id", document_id).eq("fascicolo_id", str(property_id)).execute().data
    except Exception as exc:
        raise HTTPException(502, "Impossibile aggiornare il documento") from exc
    if not updated:
        raise HTTPException(404, "Documento non trovato in questa pratica")
    return {"document_id": document_id, "superseded_by": body.replaced_by, "superseded_at": stamp}


@router.delete("/properties/{property_id}/documents/{document_id}/supersede")
def restore_document(property_id: int, document_id: int, client=Depends(user_client)):
    """Undo a replacement: the document counts in the checks again."""
    get_property(property_id, client)
    try:
        updated = client.table("documents").update({"superseded_by": None, "superseded_at": None})             .eq("id", document_id).eq("fascicolo_id", str(property_id)).execute().data
    except Exception as exc:
        raise HTTPException(502, "Impossibile aggiornare il documento") from exc
    if not updated:
        raise HTTPException(404, "Documento non trovato in questa pratica")
    return {"document_id": document_id, "superseded_by": None}


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
    content = await file.read(MAX_FILE_SIZE + 1)
    try:
        validate_file(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Use a basename even when the browser submits a Windows/Unix path.
    filename = re.split(r"[\\/]", file.filename or "documento")[-1]
    filename = "".join(c for c in filename if ord(c) >= 32) or "documento"
    intake = IntakeRecord.from_bytes(
        property_id=property_id, filename=filename,
        content=content, media_type=file.content_type,
    )
    try:
        duplicate = client.table("documents").select("id,file_name").eq("fascicolo_id", str(property_id))             .eq("content_sha256", intake.checksum_sha256).limit(1).execute().data
    except Exception as exc:
        raise HTTPException(502, "Document service unavailable") from exc
    if duplicate:
        raise HTTPException(409, f"Questo file è già stato caricato per questo immobile ({duplicate[0].get('file_name')}).")

    from document_engine.validation_rules import VERSION as validation_version
    run = PipelineRun(
        property_id=property_id,
        component_versions={"intake": "1.0", "ocr": "2.0", "extraction": "2.0", "cross_validation": validation_version},
    )
    _best_effort_insert(client, "smartbuy_analysis_runs", run.model_dump(mode="json"))
    _best_effort_insert(client, "smartbuy_run_stages", PipelineStage.completed(
        run.run_id, "document_intake", output_refs=[intake.intake_id],
        metadata={"checksum_sha256": intake.checksum_sha256, "size_bytes": intake.size_bytes},
    ).model_dump(mode="json"))

    try:
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
            include_ocr_text=True,
        )
        if getattr(result, "status_code", 500) >= 400:
            run.status = "failed"
            run.completed_at = now_iso()
            run.error = "Document reading or extraction failed"
            _best_effort_insert(client, "smartbuy_analysis_runs", run.model_dump(mode="json"))
            try:
                detail = json.loads(result.body).get("error", "Document analysis failed")
            except Exception:
                detail = "Document analysis failed"
            if any(marker in str(detail) for marker in ("insufficient_quota", "credit_balance_exhausted")):
                raise HTTPException(503, "Credito del servizio AI (OpenAI) esaurito: ricaricalo e riprova il caricamento.")
            raise HTTPException(result.status_code if result.status_code in {400, 413, 422, 429, 503, 504} else 502,
                                "Analisi del documento non completata. Riprova o verifica il file.")

        try:
            payload = json.loads(result.body)
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(502, "Risposta del servizio di analisi non valida") from exc
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise HTTPException(502, "Il servizio non ha completato l'analisi")
        ocr_text = payload.pop("ocr_text", None)
        if not isinstance(ocr_text, str):
            ocr_text = None
        if not isinstance(payload.get("extracted_fields"), dict):
            raise HTTPException(502, "Campi estratti non validi")
        for key in ("red_flags", "consistency_discrepancies"):
            if payload.get(key) is not None and not isinstance(payload[key], list):
                raise HTTPException(502, "Risultati di verifica non validi")
        if payload.get("extraction_disagreements") is not None and not isinstance(payload["extraction_disagreements"], dict):
            raise HTTPException(502, "Seconda lettura non valida")
        for key in ("extraction_confidence", "ocr_confidence"):
            payload[key] = _confidence(payload.get(key))
        if payload.get("document_type") in (None, "", "altro") and not payload.get("extracted_fields"):
            run.status = "failed"
            run.completed_at = now_iso()
            run.error = "Unsupported document"
            _best_effort_insert(client, "smartbuy_analysis_runs", run.model_dump(mode="json"))
            raise HTTPException(422, "Il file non sembra un documento immobiliare riconosciuto (visura, APE, atto, planimetria…). Non è stato salvato.")
        now = datetime.now(timezone.utc).isoformat()
        document = _insert_one(client, "documents", {
            "agente_id": client.smartbuy_user_id,
            "fascicolo_id": str(property_id),
            "content_sha256": intake.checksum_sha256,
            "file_name": filename,
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
        analysis = _insert_one(client, "document_analyses", {
            "property_id": property_id,
            "document_id": document["id"],
            "document_name": filename,
            "document_type": payload.get("document_type"),
            "confidence_score": payload.get("extraction_confidence"),
            "analysis_status": "completed",
            "extracted_data": payload.get("extracted_fields"),
            "warnings": (payload.get("red_flags") or []) + (payload.get("consistency_discrepancies") or []),
            "analyzed_at": payload.get("processed_at") or now,
        })
        original_path = store_original(
            client, property_id=property_id, document_id=document["id"], filename=filename,
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
            unsupported_fields=_unsupported_fields(payload),
        )
        _save_ocr_text(client, document, ocr_text)
        run.status = "completed"
        run.completed_at = now_iso()
        _best_effort_insert(client, "smartbuy_analysis_runs", run.model_dump(mode="json"))
        for name in ("ocr", "classification", "extraction"):
            _best_effort_insert(client, "smartbuy_run_stages", PipelineStage.completed(
                run.run_id, name, input_refs=[str(document["id"])], output_refs=[str(analysis["id"])],
                metadata=payload.get("ocr_metadata", {}) if name == "ocr" else {"verification": payload.get("verification"), "second_reading_status": payload.get("second_reading_status")} if name == "extraction" else {},
            ).model_dump(mode="json"))
        evidence = OperationalEvidence(
            evidence_id=stable_id("evidence", property_id, document["id"], analysis["id"]),
            property_id=property_id, run_id=run.run_id, document_id=str(document["id"]),
            kind="document_analysis", source_mode=SourceMode.ACCOUNT_UPLOAD,
            source_name=filename, confidence=payload.get("extraction_confidence"),
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
            "organization": _organization(payload, filename),
            "fascicolo": _fascicolo_review(client, property_id, document, payload, filename, intake.checksum_sha256, ocr_text),
            "warnings": [] if original_path is not None else [
                "Analisi salvata, ma originale non archiviato: verifica lo Storage."
            ],
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

    except HTTPException:
        _mark_failed(client, run)
        raise
    except Exception as exc:
        _mark_failed(client, run)
        raise HTTPException(502, "Pipeline non completata. Verifica i record salvati prima di riprovare.") from exc
