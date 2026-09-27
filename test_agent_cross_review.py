from datetime import date
from document_engine.cross_validation import cross_validate
from document_engine.agent_review import build_agent_review
from test_cross_validation import fact


def test_non_ape_expiry_is_not_called_expired_ape():
    docs=[{"id":1,"document_type":"contratto_locazione","extracted_fields":{"data_scadenza":"2020-01-01","data_emissione":"2000-01-01"}}]
    assert not any(f.field=="ape.scadenza" for f in cross_validate(1,documents=docs))


def test_ape_dates_produce_one_finding_per_source():
    docs=[{"id":1,"document_type":"ape","extracted_fields":{"data_scadenza":"2020-01-01","data_emissione":"2010-01-01"}}]
    matches=[f for f in cross_validate(1,documents=docs) if f.field=="ape.scadenza"]
    assert len(matches)==1


def test_low_confidence_disagreement_requires_review_not_conflict():
    findings=cross_validate(1,facts=[fact("foglio","1",doc=1,conf=0),fact("foglio","2",doc=2)])
    assert [f.status for f in findings]==["attention"]
    assert findings[0].canonical_value is None


def test_unstable_source_cannot_confirm_agreement():
    findings=cross_validate(1,facts=[fact("foglio","1",doc=1),fact("foglio","2",doc=1),fact("foglio","1",doc=2)])
    assert {f.status for f in findings}=={"attention","extraction_unstable"}


def test_multiunit_document_is_not_treated_as_bad_ocr():
    docs=[{"id":1,"extracted_fields":{"riferimenti_catastali":[{"foglio":"1","particella":"10","subalterno":"2"},{"foglio":"1","particella":"10","subalterno":"3"}]}}]
    findings=cross_validate(1,documents=docs)
    assert len(findings)==1
    assert findings[0].field=="catasto.unita_multiple"
    assert findings[0].sources==["doc:1"]
    assert findings[0].status=="attention"


def test_repeated_same_unit_is_not_multiunit():
    ref={"foglio":"1","particella":"10","subalterno":"2"}
    findings=cross_validate(1,documents=[{"id":1,"extracted_fields":{"riferimenti_catastali":[ref,ref]}}])
    assert not any(f.field=="catasto.unita_multiple" for f in findings)


def test_leased_sale_has_specific_next_action_and_no_invented_evidence():
    review=build_agent_review(1,{"contract":"vendita","workflow_context":{"occupancy":"leased"}},[{"id":1,"document_type":"ape"}],[])
    assert "vendita" in review["next_action"]["next_step"]
    assert review["next_action"]["sources"]==[]
    assert review["assessment"]=="needs_review"


def test_existing_lease_resolves_document_request():
    review=build_agent_review(1,{"workflow_context":{"occupancy":"leased"}},[{"document_type":"contratto_locazione"}],[])
    assert not review["actions"]
    assert review["assessment"]!="compliant"


def test_commercial_use_unknown_and_known_have_different_steps():
    prop={"typology":"laboratorio","contract":"affitto"}
    docs=[{"document_type":"visura_catastale"}]
    unknown=build_agent_review(1,prop,docs,[])
    known=build_agent_review(1,{**prop,"workflow_context":{"intended_use":"Restauro"}},docs,[])
    assert "Definisci" in unknown["next_action"]["title"]
    assert "Raccogli" in known["next_action"]["title"]


def test_actions_retain_sources_and_finding_ids():
    findings=cross_validate(1,facts=[fact("foglio","1",doc=1),fact("foglio","2",doc=2)])
    review=build_agent_review(1,{},[{"id":1}],findings)
    assert review["next_action"]["sources"]==["doc:1","doc:2"]
    assert review["next_action"]["finding_ids"]==[findings[0].finding_id]
    assert review==build_agent_review(1,{},[{"id":1}],findings)

def test_rejected_fact_does_not_return_from_raw_document():
    facts=[{**fact("foglio","1",doc=1),"verification_status":"rejected"},fact("foglio","2",doc=2)]
    docs=[{"id":1,"extracted_fields":{"foglio":"1"},"extraction_confidence":.99}]
    findings=cross_validate(1,facts=facts,documents=docs)
    assert all(f.status=="insufficient_evidence" for f in findings)
    assert all("doc:1" not in f.sources for f in findings)


def test_persisted_low_confidence_is_not_overridden_by_document_confidence():
    facts=[fact("foglio","1",doc=1,conf=.2),fact("foglio","2",doc=2)]
    docs=[{"id":1,"extracted_fields":{"foglio":"1"},"extraction_confidence":.99}]
    findings=cross_validate(1,facts=facts,documents=docs)
    assert [f.status for f in findings]==["attention"]
