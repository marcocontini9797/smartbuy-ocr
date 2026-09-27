"""
FastAPI backend per ingestion documenti con OCR via OpenAI vision.
Integrato con red_flags.py, consistency.py, extraction.py.
"""

from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os
import asyncio
import re
import traceback

from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# Moduli SmartBuy
from red_flags import run_all_red_flags
from consistency import run_all_checks
from fascicolo import Fascicolo
from schemas import TipoDocumento
from document_engine.ingestion import MAX_FILE_SIZE


app = FastAPI(
    title="SmartBuy Due Diligence Ingestion API",
    version="0.1.0",
    description="OCR + Extraction + Red Flags per documenti immobiliari"
)

from document_engine.feedback_router import router as feedback_router
app.include_router(feedback_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY env var required")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "SmartBuy Document Analysis API"
    }



@app.post("/api/v1/ingest-document")
async def ingest_document(
    file: UploadFile = File(...),
    fascicolo_id: Optional[str] = Query(None),
    agente_id: Optional[str] = Query(None)
):

    start_time = datetime.now()

    try:

        # ==============================
        # STEP 1 - Validazione documento
        # ==============================

        if not file.filename:
            raise ValueError("Filename missing")


        file_ext = Path(file.filename).suffix.lower()

        allowed_exts = {
            ".pdf",
            ".jpg",
            ".jpeg",
            ".png"
        }


        if file_ext not in allowed_exts:
            raise ValueError(
                f"File type not allowed: {file_ext}"
            )


        content = await file.read(MAX_FILE_SIZE + 1)

        file_size = len(content)


        if file_size > MAX_FILE_SIZE:
            raise ValueError(
                "File too large (max 20MB)"
            )


        # ==============================
        # STEP 2 - OCR Vision
        # ==============================

        from document_engine.document_reader import read_document
        reading = await read_document(content, file_ext)
        ocr_text = reading.full_text
        if len(ocr_text) > 180_000:
            raise ValueError("Documento troppo esteso per un’analisi completa: dividilo in più file.")

        # ==============================
        # STEP 3 - Classificazione
        # ==============================

        doc_type = await _classify_document_type_via_openai(
            ocr_text
        )

        # ==============================
        # STEP 4 - Estrazione dati
        # ==============================

        extracted_data = None
        extraction_confidence = 0.0
        extraction_disagreements = {}


        try:

            from concurrent.futures import ThreadPoolExecutor
            from extraction import _apply_verification_penalty, extract_document, verify_extraction
            from document_engine.cross_validation import (
                CRITICAL_EXTRACTION_FIELDS, extraction_disagreements as compare_readings,
            )

            first_reading = await asyncio.to_thread(extract_document, ocr_text, doc_type)
            first_fields = first_reading.model_dump(mode="json", exclude_none=True)
            needs_second = bool(CRITICAL_EXTRACTION_FIELDS & {
                key for key, value in first_fields.items() if value not in (None, "", [], {})
            })
            # Verification and the second independent reading of the critical
            # fields are independent calls: run them in parallel.
            with ThreadPoolExecutor(max_workers=2) as pool:
                verification_job = pool.submit(verify_extraction, ocr_text, first_reading)
                second_job = pool.submit(extract_document, ocr_text, doc_type) if needs_second else None
                verification = await asyncio.to_thread(verification_job.result)
                try:
                    second_result = await asyncio.to_thread(second_job.result) if second_job else None
                    second_reading = second_result.model_dump(mode="json", exclude_none=True) if second_result else None
                except Exception:
                    traceback.print_exc()
                    second_reading = None

            extracted_model = _apply_verification_penalty(first_reading, verification)
            extracted_data = extracted_model.model_dump(
                mode="json",
                exclude_none=True
            )
            # Confidence = share of extracted fields the verifier found
            # supported by the OCR text (not a fixed constant).
            filled = [
                key for key, value in extracted_data.items()
                if key not in {"tipo_documento", "note_incertezza"}
                and value not in (None, "", [], {})
            ]
            if not filled:
                raise ValueError("Nessun dato estraibile dal documento")
            unsupported = {
                re.split(r"[.\[]", item.campo)[0]
                for item in verification.campi_non_supportati
            }
            extraction_confidence = round(
                1 - len(unsupported & set(filled)) / max(len(filled), 1),
                3
            ) if filled else 0.0

            # If the two readings contradict each other on a critical field,
            # the field is flagged for review.
            if needs_second and second_reading is None:
                extraction_confidence = min(extraction_confidence, 0.5)
            if second_reading:
                extraction_disagreements = compare_readings(extracted_data, second_reading)
                if extraction_disagreements:
                    extraction_confidence = min(extraction_confidence, 0.6)


        except Exception:

            print(
                "========== EXTRACTION ERROR =========="
            )

            traceback.print_exc()

            print(
                "======================================"
            )

            return JSONResponse({"status":"error", "error":"Estrazione o verifica dei dati non completata. Riprova: nessun risultato parziale è stato salvato."}, status_code=502)
        # ==============================
        # STEP 5 - Red flags
        # ==============================

        red_flags_list = []
        consistency_discrepancies = []


        if extracted_data and doc_type:

            try:

                fascicolo = Fascicolo(
                    tipo_transazione="acquisto"
                )


                if doc_type == TipoDocumento.ATTO_COMPRAVENDITA:

                    from schemas import AttoCompravendita

                    fascicolo.atto_compravendita = (
                        AttoCompravendita(**extracted_data)
                    )


                elif doc_type == TipoDocumento.VISURA_CATASTALE:

                    from schemas import VisuraCatastale

                    fascicolo.visura_catastale = (
                        VisuraCatastale(**extracted_data)
                    )


                elif doc_type == TipoDocumento.APE:

                    from schemas import APE

                    fascicolo.ape = (
                        APE(**extracted_data)
                    )


                red_flags_result = run_all_red_flags(
                    fascicolo
                )


                red_flags_list = [

                    {
                        "categoria": rf.categoria,
                        "titolo": rf.titolo,
                        "gravita": rf.gravita,
                        "descrizione": rf.descrizione[:200],
                        "riferimento": rf.riferimento,
                        "azione_consigliata": (
                            rf.azione_consigliata[:150]
                            if rf.azione_consigliata
                            else None
                        )
                    }

                    for rf in red_flags_result

                ]


            except Exception as e:

                print(
                    f"Red flags warning: {e}"
                )



        processed_time = (
            datetime.now() - start_time
        ).total_seconds()



        return JSONResponse({

            "status": "success",

            "document_type": (
                doc_type.value
                if doc_type
                else None
            ),

            "extracted_fields": extracted_data,
            "extraction_disagreements": extraction_disagreements,
            "ocr_metadata": reading.metadata(),
            "verification": verification.model_dump(mode="json"),
            "second_reading_status": "completed" if second_reading is not None else "failed" if needs_second else "not_required",

            "red_flags": red_flags_list,

            "consistency_discrepancies":
                consistency_discrepancies,

            "ocr_confidence": None,  # not measured by the vision OCR

            "extraction_confidence":
                extraction_confidence,

            "processed_at":
                datetime.now().isoformat(),

            "processing_time_seconds":
                round(processed_time, 2),

            "file_name":
                file.filename,

            "file_size_bytes":
                file_size,

            "fascicolo_id":
                fascicolo_id,

            "agente_id":
                agente_id

        })



    except Exception as e:

        print(
            f"Error in ingest_document: {e}"
        )


        return JSONResponse(

            {

                "status": "error",

                "error": str(e),

                "processed_at":
                    datetime.now().isoformat(),

                "file_name":
                    file.filename
                    if file
                    else None,

                "fascicolo_id":
                    fascicolo_id,

                "agente_id":
                    agente_id

            },

            status_code=400

        )





# ==================================================
# OCR OPENAI VISION
# ==================================================


async def _ocr_with_openai(file_bytes: bytes, file_ext: str) -> str:
    from document_engine.document_reader import read_document
    return (await read_document(file_bytes, file_ext)).full_text

# ==================================================
# DOCUMENT TYPE CLASSIFICATION
# ==================================================


async def _classify_document_type_via_openai(text: str) -> Optional[TipoDocumento]:
    # The full multipage transcription is classified with a validated schema.
    from extraction import classify_document_type
    result = await asyncio.to_thread(classify_document_type, text)
    return result.tipo_documento


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
