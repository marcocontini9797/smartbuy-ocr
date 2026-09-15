"""
FastAPI backend per ingestion documenti con OCR via OpenAI vision.
Integrato con red_flags.py, consistency.py, extraction.py (non li modifica).

Per startare:
  pip install -r requirements_api.txt
  OPENAI_API_KEY=sk-... uvicorn api_server:app --reload

Deploy su Render.com (vedi DEPLOY.md)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import base64
import httpx
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# Import moduli di due diligence (non li modifico, solo li uso)
from red_flags import run_all_red_flags
from consistency import run_all_checks
from fascicolo import Fascicolo, aggiungi_al_fascicolo
from schemas import TipoDocumento

app = FastAPI(
    title="SmartBuy Due Diligence Ingestion API",
    version="0.1.0",
    description="OCR + Extraction + Red Flags per documenti immobiliari"
)

# CORS per Supabase Edge Functions
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
    """Healthcheck per Render/hosting."""
    return {
        "status": "ok",
        "service": "SmartBuy Document Analysis API"
    }


@app.post("/api/v1/ingest-document")
async def ingest_document(
    file: UploadFile = File(...),
    fascicolo_id: Optional[str] = Query(None),
    agente_id: Optional[str] = Query(None),
):
    """
    Riceve documento (PDF/immagine), fa OCR via OpenAI vision,
    estrae campi strutturati, applica red flags.

    Args:
        file: File da analizzare (PDF, JPG, PNG)
        fascicolo_id: ID fascicolo (per tracking su DB)
        agente_id: ID agente che carica (per audit)

    Returns:
        {
            "status": "success" | "error",
            "document_type": "atto_compravendita" | ... | null,
            "extracted_fields": {...},
            "red_flags": [{categoria, titolo, gravita, descrizione}, ...],
            "consistency_discrepancies": [...],
            "ocr_confidence": 0.0-1.0,
            "extraction_confidence": 0.0-1.0,
            "processed_at": "2026-09-15T14:30:00Z",
            "file_name": "...",
            "file_size_bytes": 12345
        }
    """
    start_time = datetime.now()

    try:
        # --- STEP 1: Validazione file ---
        if not file.filename:
            raise ValueError("Filename missing")

        file_ext = Path(file.filename).suffix.lower()
        allowed_exts = {".pdf", ".jpg", ".jpeg", ".png"}
        if file_ext not in allowed_exts:
            raise ValueError(f"File type not allowed. Allowed: {allowed_exts}")

        content = await file.read()
        file_size = len(content)

        if file_size > 20_000_000:  # 20MB limit
            raise ValueError("File too large (max 20MB)")

        # --- STEP 2: OCR via OpenAI vision ---
        ocr_text = await _ocr_with_openai(content, file_ext)

        # --- STEP 3: Classificazione tipo documento ---
        # Usa il prompt di classificazione da extraction.py senza importare,
        # per evitare circular imports
        doc_type = await _classify_document_type_via_openai(ocr_text)

        # --- STEP 4: Estrazione campi (riusa extraction.py) ---
        extracted_data = None
        extraction_confidence = 0.0
        try:
            from extraction import extract_document_verified

            # extract_document_verified ritorna (dati, confidence)
            result = extract_document_verified(ocr_text, doc_type)
            if result:
                extracted_data = result
                # Se il modello Pydantic ha .dict(), usalo
                if hasattr(result, "dict"):
                    extracted_data = result.dict(exclude_none=True)
                extraction_confidence = 0.85  # Baseline, potrebbe arrivare da extract_document_verified
        except Exception as e:
            print(f"Extraction warning: {e}")
            extracted_data = None
            extraction_confidence = 0.0

        # --- STEP 5: Red flags (se documento utile) ---
        red_flags_list = []
        consistency_discrepancies = []

        if extracted_data and doc_type:
            try:
                # Crea fascicolo temporaneo per red flags check
                fascicolo = Fascicolo(tipo_transazione="acquisto")

                # Aggiungi documento estratto al fascicolo
                # (aggiungi_al_fascicolo gestisce il mapping tipo_documento → campo)
                if doc_type == TipoDocumento.ATTO_COMPRAVENDITA:
                    from schemas import AttoCompravendita
                    fascicolo.atto_compravendita = AttoCompravendita(**extracted_data)
                elif doc_type == TipoDocumento.VISURA_CATASTALE:
                    from schemas import VisuraCatastale
                    fascicolo.visura_catastale = VisuraCatastale(**extracted_data)
                elif doc_type == TipoDocumento.APE:
                    from schemas import APE
                    fascicolo.ape = APE(**extracted_data)
                # ... aggiungi altri tipi come necessario

                # Red flags
                red_flags_result = run_all_red_flags(fascicolo)
                red_flags_list = [
                    {
                        "categoria": rf.categoria,
                        "titolo": rf.titolo,
                        "gravita": rf.gravita,
                        "descrizione": rf.descrizione[:200],  # Troncato per JSON
                        "riferimento": rf.riferimento,
                        "azione_consigliata": rf.azione_consigliata[:150] if rf.azione_consigliata else None
                    }
                    for rf in red_flags_result
                ]
            except Exception as e:
                print(f"Red flags warning: {e}")
                # Non bloccare il response, ma loga l'errore

        processed_time = (datetime.now() - start_time).total_seconds()

        return JSONResponse({
            "status": "success",
            "document_type": doc_type.value if doc_type else None,
            "extracted_fields": extracted_data,
            "red_flags": red_flags_list,
            "consistency_discrepancies": consistency_discrepancies,
            "ocr_confidence": 0.92,  # Placeholder, potrebbe arrivare da vision API
            "extraction_confidence": extraction_confidence,
            "processed_at": datetime.now().isoformat(),
            "processing_time_seconds": round(processed_time, 2),
            "file_name": file.filename,
            "file_size_bytes": file_size,
            "fascicolo_id": fascicolo_id,
            "agente_id": agente_id
        })

    except Exception as e:
        print(f"Error in ingest_document: {e}")
        return JSONResponse(
            {
                "status": "error",
                "error": str(e),
                "processed_at": datetime.now().isoformat(),
                "file_name": file.filename if file else None,
                "fascicolo_id": fascicolo_id,
                "agente_id": agente_id
            },
            status_code=400
        )


async def _ocr_with_openai(file_bytes: bytes, file_ext: str) -> str:
    """
    Chiama OpenAI vision API per OCR del documento.
    Supporta PDF (va come base64 diretto) e immagini (JPG, PNG).
    """
    b64_content = base64.standard_b64encode(file_bytes).decode("utf-8")

    # Determina media type
    if file_ext == ".pdf":
        media_type = "application/pdf"
    elif file_ext in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif file_ext == ".png":
        media_type = "image/png"
    else:
        raise ValueError(f"Unsupported media type: {file_ext}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/messages",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_content
                                }
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Estrai TUTTO il testo visibile in questo documento immobiliare italiano. "
                                    "Mantieni la struttura, i numeri, le date ESATTAMENTE come appaiono. "
                                    "Non riassumere, non omettere. Includi intestazioni, dati, clausole, firme se leggibili."
                                )
                            }
                        ]
                    }
                ]
            }
        )

    if response.status_code != 200:
        raise Exception(f"OpenAI vision API error: {response.status_code} - {response.text}")

    result = response.json()
    if "content" not in result or not result["content"]:
        raise Exception("Empty response from OpenAI vision API")

    return result["content"][0]["text"]


async def _classify_document_type_via_openai(text: str) -> Optional[TipoDocumento]:
    """
    Classifica tipo di documento usando OpenAI.
    Ritorna TipoDocumento enum o None se non riconosciuto.
    """
    doc_types = [td.value for td in TipoDocumento]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "max_tokens": 50,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Sei un esperto classificatore di documenti immobiliari italiani. "
                            f"Classifica il documento in una di queste categorie:\n"
                            f"{', '.join(doc_types)}\n"
                            f"Rispondi SOLO il nome della categoria, niente altro."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Classifica questo documento:\n\n{text[:1000]}"  # Prime 1000 char
                    }
                ]
            }
        )

    if response.status_code != 200:
        return None

    result = response.json()
    classification = result["choices"][0]["message"]["content"].strip().lower()

    # Match ritorno con enum TipoDocumento
    for td in TipoDocumento:
        if td.value.lower() in classification:
            return td

    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )
