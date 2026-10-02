"""Document upload regression tests: fake provider, fake database, no paid calls."""
import asyncio
import io
import sys
from copy import deepcopy
from types import SimpleNamespace
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse
from api import document_routes as routes
from test_document_facts_persistence import FakeClient as FactsClient

PAYLOAD={"status":"success","document_type":"ape",
         "extracted_fields":{"classe_energetica":"C"},
         "extraction_confidence":.9,"verification":{}}

class Client:
    smartbuy_user_id="owner"
    def __init__(self): self.calls=[]
    def table(self,name):
        self.name=name
        return self
    def select(self,*a): return self
    def update(self,row): self.calls.append(("update",self.name,row)); return self
    def insert(self,row): self.calls.append(("insert",self.name,row)); return self
    def eq(self,*a): return self
    def limit(self,*a): return self
    def execute(self): return SimpleNamespace(data=[])

@pytest.fixture
def harness(monkeypatch):
    saved=[]
    stages=[]
    facts=[]
    client=Client()
    monkeypatch.setattr(routes,"get_property",lambda *a:{"id":1})
    monkeypatch.setattr(routes,"validate_file",lambda *a:None)
    monkeypatch.setattr(routes,"_best_effort_insert",lambda c,t,p:stages.append((t,deepcopy(p))))
    monkeypatch.setattr(routes,"_insert_one",lambda c,t,p:saved.append((t,p)) or {"id":41 if t=="documents" else "analysis",**p})
    monkeypatch.setattr(routes,"store_original",lambda *a,**k:"owner/1/document.pdf")
    monkeypatch.setattr(routes,"persist_document_facts",lambda *a,**k:facts.append(k) or 1)
    monkeypatch.setitem(sys.modules,"llm_client",SimpleNamespace(MODEL="fake-model"))
    async def ingest(**kwargs):
        client.ingest_kwargs=kwargs
        return JSONResponse({**deepcopy(PAYLOAD),**getattr(client,"extra_payload",{})})
    monkeypatch.setitem(sys.modules,"api_server",SimpleNamespace(ingest_document=ingest))
    def run():
        file=UploadFile(filename="ape.pdf",file=io.BytesIO(b"synthetic-test"))
        return asyncio.run(routes.analyze_property_document(1,file,client))
    return client,saved,stages,facts,run

def test_complete_flow_persists_facts_all_stages_and_one_evidence(harness):
    client,saved,stages,facts,run=harness
    result=run()
    assert result["status"]=="success"
    assert result["run"]["status"]=="completed"
    assert [t for t,p in saved]==["documents","document_analyses"]
    assert facts[0]["default_confidence"]==.9
    assert facts[0]["model_name"]=="fake-model"
    assert {p["name"] for t,p in stages if t=="smartbuy_run_stages"}=={"document_intake","ocr","classification","extraction"}
    assert len([1 for t,p in stages if t=="smartbuy_operational_evidence"])==1
    assert result["organization"]["recommended_folder"]=="03_Energia"
    assert result["fascicolo"]=={"compared_with":0,"needs_review":False,"items":[]}

def test_fact_write_failure_marks_run_and_document_failed(harness,monkeypatch):
    client,saved,stages,facts,run=harness
    def fail(*a,**k): raise HTTPException(502,"I dati letti dal documento non sono stati salvati: riprova a caricarlo.")
    monkeypatch.setattr(routes,"persist_document_facts",fail)
    with pytest.raises(HTTPException): run()
    runs=[p for t,p in stages if t=="smartbuy_analysis_runs"]
    assert runs[-1]["status"]=="failed"
    assert not any(p["status"]=="completed" for p in runs)
    assert ("update","documents",{"processing_status":"failed"}) in client.calls

@pytest.mark.parametrize("payload", [[],{"status":"error"}, {**PAYLOAD,"extracted_fields":[]},
                                     {**PAYLOAD,"red_flags":{}},{**PAYLOAD,"extraction_disagreements":[]}])
def test_invalid_provider_result_never_creates_canonical_rows(harness,monkeypatch,payload):
    _,saved,stages,_,run=harness
    async def ingest(**kwargs): return JSONResponse(payload)
    monkeypatch.setitem(sys.modules,"api_server",SimpleNamespace(ingest_document=ingest))
    with pytest.raises(HTTPException) as exc: run()
    assert exc.value.status_code==502
    assert not saved
    assert [p for t,p in stages if t=="smartbuy_analysis_runs"][-1]["status"]=="failed"

def test_quota_error_has_safe_actionable_message(harness,monkeypatch):
    _,saved,_,_,run=harness
    async def ingest(**kwargs):
        return JSONResponse({"error":"insufficient_quota secret-token"},status_code=500)
    monkeypatch.setitem(sys.modules,"api_server",SimpleNamespace(ingest_document=ingest))
    with pytest.raises(HTTPException) as exc: run()
    assert exc.value.status_code==503
    assert "secret-token" not in exc.value.detail
    assert not saved

def test_storage_warning_does_not_erase_valid_analysis(harness,monkeypatch):
    *_,run=harness
    monkeypatch.setattr(routes,"store_original",lambda *a,**k:None)
    result=run()
    assert result["run"]["status"]=="completed"
    assert result["original_saved"] is False and result["warnings"]

def test_second_reading_and_supported_field_parsing(harness,monkeypatch):
    _,_,_,facts,run=harness
    payload={**PAYLOAD,"extraction_disagreements":{"classe_energetica":"D"},
             "verification":{"campi_non_supportati":[None,{},{"campo":"classe_energetica"}]}}
    async def ingest(**kwargs): return JSONResponse(payload)
    monkeypatch.setitem(sys.modules,"api_server",SimpleNamespace(ingest_document=ingest))
    run()
    assert facts[0]["second_reading"]=={"classe_energetica":"D"}
    assert facts[0]["unsupported_fields"]=={"classe_energetica"}

def test_zero_confidence_and_original_second_citation_are_preserved():
    client=FactsClient()
    routes.persist_document_facts(client,property_id=1,document={"id":1},analysis={"id":"a"},
        extracted_fields={},default_confidence=.9,model_name="fake",
        second_reading={"x":{"valore":0,"confidence":0,"fonte":"Zero riportato nel documento"}})
    assert client.store["property_facts"][0]["confidence_score"]==0
    assert client.store["fact_provenance"][0]["source_text"]=="Zero riportato nel documento"

def test_unknown_confidence_is_not_invented():
    client=FactsClient()
    routes.persist_document_facts(client,property_id=1,document={"id":1},analysis={"id":"a"},
        extracted_fields={},second_reading={"x":False})
    assert client.store["property_facts"][0]["confidence_score"] is None
    assert client.store["property_facts"][0]["fact_value"]["value"] is False


def test_ocr_text_is_requested_stored_and_never_sent_to_the_browser(harness):
    client,_,_,_,run=harness
    client.extra_payload={"ocr_text":"testo ocr della visura"}
    result=run()
    assert client.ingest_kwargs["include_ocr_text"] is True
    assert "ocr_text" not in result["result"]
    stored=[row for kind,table,row in client.calls if kind=="insert" and table=="document_text_extractions"]
    assert stored==[{"document_id":41,"extraction_method":"vision_ocr","raw_text":"testo ocr della visura",
                     "character_count":len("testo ocr della visura")}]

def test_missing_or_invalid_ocr_text_stores_nothing_and_still_succeeds(harness):
    client,_,_,_,run=harness
    client.extra_payload={"ocr_text":12345}
    result=run()
    assert result["status"]=="success"
    assert not [1 for kind,table,_ in client.calls if table=="document_text_extractions"]

def test_failure_saving_the_ocr_text_does_not_fail_the_upload(harness,monkeypatch):
    client,_,_,_,run=harness
    client.extra_payload={"ocr_text":"testo"}
    def broken(row): raise RuntimeError("storage down")
    monkeypatch.setattr(client,"insert",broken)
    assert run()["status"]=="success"
