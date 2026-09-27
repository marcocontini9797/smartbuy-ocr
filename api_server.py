"""
FastAPI backend per ingestion documenti con OCR via OpenAI vision.
Integrato con red_flags.py, consistency.py, extraction.py.
"""

from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os
import base64
import httpx
import traceback

from datetime import datetime
from pathlib import Path
from typing import Optional
from io import BytesIO

from dotenv import load_dotenv
from pdf2image import convert_from_bytes

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


        content = await file.read()

        file_size = len(content)


        if file_size > MAX_FILE_SIZE:
            raise ValueError(
                "File too large (max 20MB)"
            )


        # ==============================
        # STEP 2 - OCR Vision
        # ==============================

        ocr_text = await _ocr_with_openai(
            content,
            file_ext
        )


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

            first_reading = extract_document(ocr_text, doc_type)
            first_fields = first_reading.model_dump(mode="json", exclude_none=True)
            needs_second = bool(CRITICAL_EXTRACTION_FIELDS & {
                key for key, value in first_fields.items() if value not in (None, "", [], {})
            })
            # Verification and the second independent reading of the critical
            # fields are independent calls: run them in parallel.
            with ThreadPoolExecutor(max_workers=2) as pool:
                verification_job = pool.submit(verify_extraction, ocr_text, first_reading)
                second_job = pool.submit(extract_document, ocr_text, doc_type) if needs_second else None
                verification = verification_job.result()
                try:
                    second_reading = second_job.result().model_dump(mode="json", exclude_none=True) if second_job else None
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
            unsupported = {
                item.campo.split(".")[0]
                for item in verification.campi_non_supportati
            }
            extraction_confidence = round(
                1 - len(unsupported & set(filled)) / max(len(filled), 1),
                3
            ) if filled else 0.0

            # If the two readings contradict each other on a critical field,
            # the field is flagged for review.
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

            extracted_data = None
            extraction_confidence = 0.0
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


async def _ocr_with_openai(
    file_bytes: bytes,
    file_ext: str
) -> str:


    """
    OCR tramite OpenAI Vision.
    I PDF vengono convertiti prima in immagini.
    """


    # PDF -> PNG

    if file_ext.lower() == ".pdf":


        images = convert_from_bytes(

            file_bytes,

            first_page=1,

            last_page=1,

            poppler_path=
                r"C:\poppler\poppler-26.09.0\Library\bin"

        )


        buffer = BytesIO()


        images[0].save(
            buffer,
            format="PNG"
        )


        image_bytes = buffer.getvalue()


        b64_content = base64.b64encode(
            image_bytes
        ).decode("utf-8")


        media_type = "image/png"



    else:


        b64_content = base64.b64encode(
            file_bytes
        ).decode("utf-8")


        if file_ext.lower() in [
            ".jpg",
            ".jpeg"
        ]:

            media_type = "image/jpeg"


        else:

            media_type = "image/png"



    async with httpx.AsyncClient(
        timeout=120.0
    ) as client:


        response = await client.post(


            "https://api.openai.com/v1/chat/completions",


            headers={

                "Authorization":
                    f"Bearer {OPENAI_API_KEY}",

                "Content-Type":
                    "application/json"

            },


            json={

                "model":
                    "gpt-4o",


                "max_tokens":
                    4096,


                "messages":[

                    {

                        "role":
                            "user",


                        "content":[


                            {

                                "type":
                                    "text",

                                "text":
                                    (
                                    "Estrai tutto il testo "
                                    "presente nel documento immobiliare. "
                                    "Mantieni numeri catastali, "
                                    "date, intestazioni e valori "
                                    "esattamente come appaiono."
                                    )

                            },


                            {

                                "type":
                                    "image_url",


                                "image_url":{

                                    "url":
                                    (
                                    f"data:{media_type};"
                                    f"base64,{b64_content}"
                                    )

                                }

                            }


                        ]

                    }

                ]

            }

        )


    if response.status_code != 200:

        raise Exception(

            f"OpenAI API error: "
            f"{response.status_code} - "
            f"{response.text}"

        )


    result = response.json()


    return (
        result["choices"][0]
        ["message"]["content"]
    )
# ==================================================
# DOCUMENT TYPE CLASSIFICATION
# ==================================================


async def _classify_document_type_via_openai(
    text: str
) -> Optional[TipoDocumento]:

    """
    Classifica il tipo di documento immobiliare.
    Ritorna TipoDocumento oppure None.
    """


    doc_types = [
        td.value
        for td in TipoDocumento
    ]



    async with httpx.AsyncClient(
        timeout=30.0
    ) as client:


        response = await client.post(


            "https://api.openai.com/v1/chat/completions",


            headers={

                "Authorization":
                    f"Bearer {OPENAI_API_KEY}",

                "Content-Type":
                    "application/json"

            },


            json={

                "model":
                    "gpt-4o",


                "max_tokens":
                    50,


                "messages":[


                    {

                        "role":
                            "system",


                        "content":
                            (
                            "Sei un esperto classificatore "
                            "di documenti immobiliari italiani. "

                            "Classifica il documento in una "
                            "di queste categorie:\n"

                            f"{', '.join(doc_types)}\n\n"

                            "Rispondi SOLO con il nome "
                            "della categoria."
                            )

                    },


                    {

                        "role":
                            "user",


                        "content":
                            (
                            "Classifica questo documento:\n\n"
                            f"{text[:2000]}"
                            )

                    }

                ]

            }

        )



    if response.status_code != 200:

        return None



    result = response.json()


    classification = (
        result["choices"][0]
        ["message"]["content"]
        .strip()
        .lower()
    )



    for td in TipoDocumento:

        if td.value.lower() in classification:

            return td



    return None





# ==================================================
# START SERVER
# ==================================================


if __name__ == "__main__":

    import uvicorn


    uvicorn.run(

        app,

        host="0.0.0.0",

        port=int(
            os.getenv(
                "PORT",
                8000
            )
        )

    )
