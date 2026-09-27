import asyncio
from io import BytesIO
import httpx
import pytest
from PIL import Image
from pydantic import BaseModel
from document_engine import document_reader as reader
from schemas import CampoEstratto, VerificationResult, CampoNonSupportato
from extraction import _apply_verification_penalty


def test_multipage_order_and_bounded_rendering(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","test")
    monkeypatch.setenv("OCR_CONCURRENCY","2")
    monkeypatch.setattr(reader,"pdfinfo_from_bytes",lambda *a,**k:{"Pages":5})
    batches=[]
    def render(*a,**kw):
        batches.append((kw["first_page"],kw["last_page"]))
        return [Image.new("RGB",(10,10)) for _ in range(kw["last_page"]-kw["first_page"]+1)]
    async def read(client,image,number,*a):
        await asyncio.sleep(0.001 * (6-number))
        return reader.PageReading(number,f"Dato importante pagina {number}")
    monkeypatch.setattr(reader,"convert_from_bytes",render)
    monkeypatch.setattr(reader,"transcribe_page",read)
    result=asyncio.run(reader.read_document(b"pdf",".pdf"))
    assert batches == [(1,2),(3,4),(5,5)]
    assert [p.page_number for p in result.pages] == [1,2,3,4,5]
    assert "Dato importante pagina 5" in result.full_text
    assert result.metadata()["confidence"] is None


def test_oversized_pdf_rejected_before_render_or_ai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","test")
    monkeypatch.setenv("OCR_MAX_PAGES","2")
    monkeypatch.setattr(reader,"pdfinfo_from_bytes",lambda *a,**k:{"Pages":3})
    monkeypatch.setattr(reader,"convert_from_bytes",lambda *a,**k:pytest.fail("Must not render"))
    with pytest.raises(reader.OCRFailure,match="3 pagine"):
        asyncio.run(reader.read_document(b"pdf",".pdf"))


def test_page_failure_never_becomes_partial_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","test")
    monkeypatch.setattr(reader,"pdfinfo_from_bytes",lambda *a,**k:{"Pages":2})
    monkeypatch.setattr(reader,"convert_from_bytes",lambda *a,**k:[Image.new("RGB",(10,10)),Image.new("RGB",(10,10))])
    async def read(client,image,number,*a):
        if number==2: raise reader.OCRFailure("pagina 2 illeggibile")
        return reader.PageReading(number,"Testo della prima pagina")
    monkeypatch.setattr(reader,"transcribe_page",read)
    with pytest.raises(reader.OCRFailure,match="pagina 2"):
        asyncio.run(reader.read_document(b"pdf",".pdf"))


@pytest.mark.parametrize("finish,content,refusal",[("length","testo parziale",None),("stop","",None),("stop","testo","refusal")])
def test_incomplete_provider_response_is_rejected(finish,content,refusal):
    async def run():
        transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"choices":[{"finish_reason":finish,"message":{"content":content,"refusal":refusal}}]}))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(reader.OCRFailure):
                await reader.transcribe_page(client,Image.new("RGB",(10,10)),2,"test","key")
    asyncio.run(run())


def test_auth_error_not_retried_or_leaked():
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(401,text="SECRET upstream body")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(reader.OCRFailure) as exc:
                await reader.transcribe_page(client,Image.new("RGB",(10,10)),1,"test","key")
            assert "SECRET" not in str(exc.value)
    asyncio.run(run())
    assert len(calls)==1


def test_mismatched_image_extension_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","test")
    buffer=BytesIO();Image.new("RGB",(10,10)).save(buffer,format="PNG")
    with pytest.raises(reader.OCRFailure,match="estensione"):
        asyncio.run(reader.read_document(buffer.getvalue(),".jpg"))


def test_nested_field_penalty_does_not_affect_sibling():
    class Extracted(BaseModel):
        values:list[CampoEstratto]
        note_incertezza:list[str]=[]
    data=Extracted(values=[CampoEstratto(valore="42",confidence=.9),CampoEstratto(valore="43",confidence=.9)])
    verdict=VerificationResult(tutti_i_campi_supportati=True,campi_non_supportati=[CampoNonSupportato(campo="values[0].valore",valore_estratto="42",motivo="assente",gravita="alta")])
    result=_apply_verification_penalty(data,verdict)
    assert result.values[0].confidence==.2
    assert result.values[1].confidence==.9
    assert data.values[0].confidence==.9
    assert result.note_incertezza

def test_ingestion_uses_all_pages_and_fails_on_extraction_error(monkeypatch):
    import json
    import api_server
    import extraction
    from fastapi import UploadFile
    from schemas import TipoDocumento, APE
    reading=reader.DocumentReading([reader.PageReading(1,"Prima pagina"),reader.PageReading(2,"Classe energetica C")],0.1,"test")
    async def read(*args):return reading
    async def classify(text):
        assert "Classe energetica C" in text
        return TipoDocumento.APE
    def extract(text,kind):
        assert "--- PAGINA 2 ---" in text
        return APE(classe_energetica="C")
    monkeypatch.setattr(reader,"read_document",read)
    monkeypatch.setattr(api_server,"_classify_document_type_via_openai",classify)
    monkeypatch.setattr(extraction,"extract_document",extract)
    monkeypatch.setattr(extraction,"verify_extraction",lambda *a:VerificationResult(tutti_i_campi_supportati=True))
    result=asyncio.run(api_server.ingest_document(UploadFile(file=BytesIO(b"pdf"),filename="test.pdf"),"1","u"))
    assert result.status_code==200
    payload=json.loads(result.body)
    assert payload["ocr_metadata"]["page_count"]==2
    assert payload["extracted_fields"]["classe_energetica"]=="C"
    def fail(*a):raise RuntimeError("upstream failed")
    monkeypatch.setattr(extraction,"extract_document",fail)
    failed=asyncio.run(api_server.ingest_document(UploadFile(file=BytesIO(b"pdf"),filename="test.pdf"),"1","u"))
    assert failed.status_code==502
    assert json.loads(failed.body)["status"]=="error"


def test_real_pdf_renderer_preserves_three_pages(monkeypatch):
    if not reader.poppler_path():pytest.skip("Poppler not installed")
    monkeypatch.setenv("OPENAI_API_KEY","test")
    buffer=BytesIO()
    images=[Image.new("RGB",(120,120),color) for color in ["red","green","blue"]]
    images[0].save(buffer,format="PDF",save_all=True,append_images=images[1:])
    async def read(client,image,number,*a):return reader.PageReading(number,f"Page {number}")
    monkeypatch.setattr(reader,"transcribe_page",read)
    result=asyncio.run(reader.read_document(buffer.getvalue(),".pdf"))
    assert len(result.pages)==3
