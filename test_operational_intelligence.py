from core.operational_models import DocumentRequest, IntakeRecord, PipelineStage
from document_engine.operational_services import cross_validate_facts, route_ape_source, validate_gis
from document_engine.external_sources import source_plan
from document_engine.acquisition_engine import build_acquisition_plan


def test_intake_ids_are_stable_and_checksum_sensitive():
    first = IntakeRecord.from_bytes(property_id=16, filename="ape.pdf", content=b"same")
    second = IntakeRecord.from_bytes(property_id=16, filename="renamed.pdf", content=b"same")
    changed = IntakeRecord.from_bytes(property_id=16, filename="ape.pdf", content=b"changed")
    assert first.intake_id == second.intake_id
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.intake_id != changed.intake_id


def test_stage_and_document_request_ids_are_idempotent():
    assert PipelineStage.completed("run-a", "ocr").stage_id == PipelineStage.completed("run-a", "ocr").stage_id
    one = DocumentRequest.create(property_id=16, document_type="ape", requested_from="seller", reason="missing")
    two = DocumentRequest.create(property_id=16, document_type="ape", requested_from="seller", reason="new wording")
    assert one.request_id == two.request_id


def test_ape_routing_is_regional_and_does_not_send_bologna_to_cened():
    bologna = route_ape_source(province="BO")
    milan = route_ape_source(province="MI")
    assert bologna["name"] == "SACE Emilia-Romagna"
    assert milan["name"] == "CENED Lombardia"
    assert bologna["automatic"] is False


def test_gis_requires_coordinates_and_authoritative_boundary_check():
    assert validate_gis(latitude=None, longitude=None, expected_city="Bologna")["status"] == "insufficient_evidence"
    result = validate_gis(latitude=44.4949, longitude=11.3426, expected_city="Bologna")
    assert result["status"] == "coordinates_valid"
    assert result["requires_authoritative_boundary_check"] is True


def test_cross_validation_preserves_sources_and_flags_conflicts():
    facts = [
        {"id": "f1", "fact_name": "energy_class", "fact_value": {"value": "C"}, "source_type": "listing", "evidence_ids": ["e1"]},
        {"id": "f2", "fact_name": "energy_class", "fact_value": {"value": "D"}, "source_type": "seller_document", "evidence_ids": ["e2"]},
        {"id": "f3", "fact_name": "city", "fact_value": {"value": "Bologna"}, "source_type": "listing"},
        {"id": "f4", "fact_name": "city", "fact_value": {"value": "bologna"}, "source_type": "gis"},
    ]
    findings = {item.field: item for item in cross_validate_facts(16, facts)}
    assert findings["classe_energetica"].status == "conflict"
    assert findings["classe_energetica"].evidence_ids == ["e1", "e2"]
    assert findings["catasto.comune"].status == "consistent"


def test_external_source_plan_is_truthful_about_access_and_region():
    plan = source_plan(province="BO", available_inputs={"ape_code", "latitude", "longitude"})
    sources = {item["source_id"]: item for item in plan["sources"]}
    assert "sace_er" in sources and "cened_lombardia" not in sources
    assert sources["sace_er"]["status"] == "ready"
    assert sources["sace_er"]["requires_user_action"] is True
    assert sources["rer_geoportal"]["execution"] == "automatic"
    assert sources["seller_ape"]["verification_level"] == "supporting"


def test_acquisition_plan_prioritizes_once_and_automates_gis():
    plan = build_acquisition_plan(
        property_record={"id": 16, "province": "BO", "latitude": 44.49, "longitude": 11.34},
        documents=[], facts=[],
        existing_requests=[{"document_type": "ape", "status": "open"}],
    )
    ape = next(item for item in plan["actions"] if item["track"] == "ape")
    gis = next(item for item in plan["actions"] if item["track"] == "gis")
    assert ape["action"] == "await_existing_request"
    assert gis["action"] == "run_automatic_check" and gis["responsible_party"] == "smartbuy"
    assert plan["autonomous_actions"] == 1


def test_acquisition_plan_uses_sace_when_ape_and_code_exist():
    plan = build_acquisition_plan(
        property_record={"id": 16, "province": "BO"},
        documents=[{"document_type": "ape"}],
        facts=[{"fact_name": "ape_code", "fact_value": {"value": "TEST-CODE"}}],
        existing_requests=[],
    )
    ape = next(item for item in plan["actions"] if item["track"] == "ape")
    assert ape["action"] == "open_assisted_check"
    assert ape["source_id"] == "sace_er"
