"""ingest_document returns the OCR text only when asked (offline: reader and AI are stubbed)."""
import asyncio
import io
import json

import pytest
from fastapi import UploadFile

import api_server
import extraction
from document_engine import document_reader
from schemas import APE, TipoDocumento, VerificationResult

OCR_TEXT = "Attestato di prestazione energetica: classe energetica C, valido fino al 2030."


@pytest.fixture(autouse=True)
def stubbed_providers(monkeypatch):
    async def read(content, extension):
        return document_reader.DocumentReading([document_reader.PageReading(1, OCR_TEXT)], 0.1, "stub-model")

    async def classify(text):
        return TipoDocumento.APE

    monkeypatch.setattr(document_reader, "read_document", read)
    monkeypatch.setattr(api_server, "_classify_document_type_via_openai", classify)
    monkeypatch.setattr(extraction, "extract_document", lambda text, doc_type: APE(classe_energetica="C"))
    monkeypatch.setattr(extraction, "verify_extraction",
                        lambda text, extracted: VerificationResult(tutti_i_campi_supportati=True))


def ingest(**kwargs):
    file = UploadFile(filename="ape.pdf", file=io.BytesIO(b"%PDF-1.4 synthetic"))
    response = asyncio.run(api_server.ingest_document(file=file, fascicolo_id="1", agente_id="user", **kwargs))
    return response.status_code, json.loads(response.body)


def test_ocr_text_is_returned_when_requested():
    status, body = ingest(include_ocr_text=True)
    assert status == 200 and body["status"] == "success"
    assert OCR_TEXT in body["ocr_text"]
    assert body["extracted_fields"]["classe_energetica"] == "C"


def test_ocr_text_is_not_returned_by_default_over_http():
    status, body = ingest(include_ocr_text=False)
    assert status == 200 and "ocr_text" not in body


def test_calling_the_function_directly_without_the_argument_does_not_leak_the_text():
    # Called as a plain function, an omitted parameter keeps its Query(...) default
    # object, which is truthy: the response must still not carry the text.
    status, body = ingest()
    assert status == 200 and "ocr_text" not in body
