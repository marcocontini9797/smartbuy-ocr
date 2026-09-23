from core.property_flow_models import PropertyPurpose, RequirementLevel
from document_engine.property_flow_playbooks import get_property_playbook


def test_sale_playbook_contains_transfer_checks():
    playbook = get_property_playbook(PropertyPurpose.SALE)
    ids = {item.requirement_id for item in playbook.requirements}
    assert "sale.provenance" in ids
    assert "sale.cadastral_conformity" in ids
    assert "sale.encumbrances" in ids
    assert "rent.registration" not in ids


def test_long_rent_contains_registration_without_short_rent_rules():
    playbook = get_property_playbook(PropertyPurpose.RENT_LONG_TERM)
    ids = {item.requirement_id for item in playbook.requirements}
    assert "rent.registration" in ids
    assert "short_rent.cin" not in ids


def test_short_rent_adds_cin_safety_and_local_rules():
    playbook = get_property_playbook(PropertyPurpose.RENT_SHORT_TERM)
    ids = {item.requirement_id for item in playbook.requirements}
    assert {"short_rent.cin", "short_rent.safety", "short_rent.local_rules"} <= ids


def test_sale_marks_condominium_as_recommended_and_transfer_checks_as_mandatory():
    playbook = get_property_playbook(PropertyPurpose.SALE)
    levels = {item.requirement_id: item.level for item in playbook.requirements}
    assert levels["sale.cadastral_conformity"] == RequirementLevel.MANDATORY
    assert levels["sale.encumbrances"] == RequirementLevel.MANDATORY
    assert levels["sale.condominium"] == RequirementLevel.HIGHLY_RECOMMENDED


def test_rent_marks_registration_mandatory_and_inventory_recommended():
    playbook = get_property_playbook(PropertyPurpose.RENT_LONG_TERM)
    levels = {item.requirement_id: item.level for item in playbook.requirements}
    assert levels["rent.registration"] == RequirementLevel.MANDATORY
    assert levels["rent.condition"] == RequirementLevel.HIGHLY_RECOMMENDED
