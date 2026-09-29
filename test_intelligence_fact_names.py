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


def test_missing_information_is_a_gap_not_a_risk():
    result = build_property_intelligence(
        property_record={"id": 7, "address": "Via Zamboni 33", "city": "Bologna"},
        facts=[], documents=[], analyses=[], provenance=[],
    )
    assert result["risks"] == []
    assert result["summary"]["open_risks"] == 0
    assert result["summary"]["missing_items"] == len(result["gaps"]) > 0
    energy = next(g for g in result["gaps"] if g["area"] == "energy")
    assert energy["title"] == "Dati energetici da raccogliere" and energy["action"] == "Carica l'APE"


def test_cross_validation_conflict_blocks_intelligence_readiness():
    facts = [
        {
            "id": "f1",
            "fact_name": "riferimento",
            "fact_value": {"value": {"comune": "Bologna", "foglio": "123", "particella": "456", "subalterno": "7", "categoria": "A/3"}},
            "source_type": "document",
            "source_document_id": 101,
            "confidence_score": 0.99,
            "verification_status": "unverified",
        },
        {
            "id": "f2",
            "fact_name": "riferimento",
            "fact_value": {"value": {"comune": "Bologna", "foglio": "123", "particella": "456", "subalterno": "7", "categoria": "A/2"}},
            "source_type": "document",
            "source_document_id": 102,
            "confidence_score": 0.99,
            "verification_status": "unverified",
        },
    ]
    documents = [
        {
            "id": 101,
            "document_type": "visura_catastale",
            "processing_status": "completed",
            "extracted_fields": {
                "riferimento": {
                    "comune": "Bologna",
                    "foglio": "123",
                    "particella": "456",
                    "subalterno": "7",
                    "categoria": "A/3",
                }
            },
        },
        {
            "id": 102,
            "document_type": "visura_catastale",
            "processing_status": "completed",
            "extracted_fields": {
                "riferimento": {
                    "comune": "Bologna",
                    "foglio": "123",
                    "particella": "456",
                    "subalterno": "7",
                    "categoria": "A/2",
                }
            },
        },
    ]
    result = build_property_intelligence(
        property_record={"id": 9, "address": "Via Giuseppe Verdi 10", "city": "Bologna"},
        facts=facts,
        documents=documents,
        analyses=[{"id": 1}, {"id": 2}],
        provenance=[],
    )

    assert result["summary"]["readiness_level"] != "ready"
    assert result["summary"]["open_risks"] >= 1
    risk = next(item for item in result["risks"] if item["category"] == "factual_discrepancy")
    assert risk["severity"] == "high"
    assert "catasto.categoria" in risk["title"]
