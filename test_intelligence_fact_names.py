from api.intelligence_service import build_property_intelligence


def row(name, value, fid):
    return {"id": fid, "fact_name": name, "fact_value": {"value": value}, "source_type": "document",
            "source_document_id": 41, "confidence_score": 0.9, "verification_status": "unverified"}


def test_uploaded_ape_and_atto_fields_reach_the_profile():
    result = build_property_intelligence(
        property_record={"id": 5, "address": "Via Vizzani 72", "city": "Bologna"},
        facts=[
            row("classe_energetica", "C", "f1"),
            row("riferimenti_catastali", [{"foglio": "285", "particella": "789", "subalterno": "2", "categoria": "A/2"}], "f2"),
        ],
        documents=[], analyses=[], provenance=[],
    )
    profile = result["profile"]
    assert profile["energy_certificate"]["energy_class"] == "C"
    assert profile["cadastral"]["foglio"] == "285"
    assert profile["cadastral"]["category"] == "A/2"
