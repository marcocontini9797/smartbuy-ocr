import pytest
from pydantic import ValidationError
from document_engine.workflow_context import WorkflowContext
from document_engine.document_acquisition import build_document_packages
from document_engine.checklist import build_checklist
from document_engine.typology import TYPOLOGIES

def plan(record):
    result = build_document_packages({"id":1, **record}, [], [])
    return {i["document_type"] for g in result["packages"] for i in g["items"]}, result["applicability_checks"]

def checklist(record):
    return {i["key"]:i for i in build_checklist(property_record={"id":1, **record}, documents=[], findings=[])["items"]}

@pytest.mark.parametrize("typology", list(TYPOLOGIES))
@pytest.mark.parametrize("contract", ["vendita", "affitto"])
def test_every_supported_property_has_consistent_conditional_requests(typology, contract):
    record = {"typology":typology,"contract":contract,"is_condominio":False,
              "workflow_context":{"occupancy":"vacant","fire_safety":False,"activity_documents":False,"ape_applicable":False}}
    requests, questions = plan(record)
    checks = checklist(record)
    assert "certificato_prevenzione_incendi" not in requests
    assert checks["certificato_prevenzione_incendi"]["applicable"] is False
    assert "contratto_locazione" not in requests
    assert "regolamento_condominiale" not in requests
    assert ("ispezione_ipotecaria" in requests) == (contract == "vendita")
    if typology == "box":
        assert "ape" not in requests and "ape" not in checks
    if TYPOLOGIES[typology].asset == "commerciale":
        assert "titoli_edilizi" in requests  # also in commercial leases
        assert checks["ape"]["applicable"] is False

@pytest.mark.parametrize("answer", [None, False, True])
def test_specialist_applicability_is_shared(answer):
    record={"typology":"laboratorio","contract":"affitto","workflow_context":{"activity_documents":answer,"fire_safety":answer}}
    requests,questions=plan(record); checks=checklist(record)
    for key in ["scia_licenza_commerciale","certificato_prevenzione_incendi"]:
        assert (key in requests) == (answer is True)
        assert any(q["document_type"] == key for q in questions) == (answer is None)
        if answer is None:
            assert checks[key]["status"] == "to_check"
            assert checks[key]["requirement"] == "conditional"
        elif answer is False:
            assert checks[key]["applicable"] is False

def test_canonical_contract_condominium_and_lease_drive_requests():
    requests,_=plan({"contract":"vendita","is_condominio":True,"workflow_context":{"occupancy":"leased"}})
    assert {"titoli_edilizi","regolamento_condominiale","contratto_locazione","ricevuta_rli"} <= requests

def test_invalid_answers_are_rejected():
    with pytest.raises(ValidationError): WorkflowContext(occupancy="maybe")
    with pytest.raises(ValidationError): WorkflowContext(intended_use="a"*301)
    with pytest.raises(ValidationError): WorkflowContext(unknown_field=True)

def test_unknown_does_not_become_a_specialist_document_request():
    requests,questions=plan({"typology":"ufficio","contract":"affitto"})
    assert "ape" not in requests
    assert any(q["document_type"]=="ape" for q in questions)
    assert checklist({"typology":"ufficio"})["ape"]["status"] == "to_check"

def test_property_update_preserves_unanswered_context(monkeypatch):
    from api import property_routes
    from test_properties_and_originals import FakeClient
    current={"id":1,"workflow_context":{"occupancy":"leased","fire_safety":True}}
    monkeypatch.setattr(property_routes,"get_property",lambda *args:current)
    client=FakeClient()
    property_routes.update_property(1,property_routes.PropertyUpdate(workflow_context={"fire_safety":None}),client)
    update=next(c[2] for c in client.calls if c[0]=="update")
    assert update["workflow_context"] == {"occupancy":"leased","fire_safety":None}

def test_create_laboratory_preserves_workflow_and_owner():
    from api.property_routes import NewProperty, create_property
    from test_properties_and_originals import FakeClient
    client=FakeClient()
    result=create_property(NewProperty(address="Via test 1",city="Bologna",typology="laboratorio",contract="affitto",workflow_context={"occupancy":"vacant","intended_use":"Restauro"}),client)
    assert result["property_type"] == "commerciale"
    assert result["workflow_context"]["intended_use"] == "Restauro"
    assert result["user_id"] == client.smartbuy_user_id
