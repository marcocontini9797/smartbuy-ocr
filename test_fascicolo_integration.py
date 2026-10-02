from document_engine.fascicolo_integration import (
    build_fascicolo_comparisons,
)


def test_integration_detects_duplicate():
    payload = {
        "document_type": "visura_catastale",
        "document_series_id": "VISURA-BOLOGNA-10-20-5",
        "document_date": "2026-01-01",
        "ocr_text": """
        VISURA CATASTALE
        COMUNE DI BOLOGNA
        FOGLIO 10
        PARTICELLA 20
        SUBALTERNO 5
        MARCO ROSSI
        """,
        "extracted_fields": {
            "comune": "Bologna",
            "foglio": "10",
            "particella": "20",
            "subalterno": "5",
        },
    }

    existing_documents = [
        {
            "id": "doc-001",
            "file_name": "visura_originale.pdf",
            "content_sha256": (
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ),
            "document_type": "visura_catastale",
            "document_series_id": "VISURA-BOLOGNA-10-20-5",
            "document_date": "2026-01-01",
            "ocr_text": """
            VISURA CATASTALE
            COMUNE DI BOLOGNA
            FOGLIO 10
            PARTICELLA 20
            SUBALTERNO 5
            MARCO ROSSI
            """,
            "extracted_fields": {
                "comune": "Bologna",
                "foglio": "10",
                "particella": "20",
                "subalterno": "5",
            },
        }
    ]

    result = build_fascicolo_comparisons(
        payload,
        new_document_id="doc-002",
        filename="visura_nuova.pdf",
        sha256=(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        existing_documents=existing_documents,
    )

    assert len(result) == 1

    comparison = result[0]

    assert comparison["existing_document_id"] == "doc-001"
    assert comparison["new_document_id"] == "doc-002"

    assert comparison["similarity"]["status"] == "duplicate"

    assert comparison["action"]["action"] == "duplicate"
    assert comparison["action"]["requires_review"] is False


def test_integration_detects_new_version():
    payload = {
        "document_type": "visura_catastale",
        "document_series_id": "VISURA-BOLOGNA-10-20-5",
        "document_date": "2026-01-01",
        "ocr_text": """
        VISURA CATASTALE AGGIORNATA
        COMUNE DI BOLOGNA
        FOGLIO 10
        PARTICELLA 20
        SUBALTERNO 5
        MARCO ROSSI
        """,
        "extracted_fields": {
            "comune": "Bologna",
            "foglio": "10",
            "particella": "20",
            "subalterno": "5",
        },
    }

    existing_documents = [
        {
            "id": "doc-001",
            "file_name": "visura_2025.pdf",
            "content_sha256": (
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ),
            "document_type": "visura_catastale",
            "document_series_id": "VISURA-BOLOGNA-10-20-5",
            "document_date": "2025-01-01",
            "ocr_text": """
            VISURA CATASTALE
            COMUNE DI BOLOGNA
            FOGLIO 10
            PARTICELLA 20
            SUBALTERNO 5
            MARCO ROSSI
            """,
            "extracted_fields": {
                "comune": "Bologna",
                "foglio": "10",
                "particella": "20",
                "subalterno": "5",
            },
        }
    ]

    result = build_fascicolo_comparisons(
        payload,
        new_document_id="doc-002",
        filename="visura_2026.pdf",
        sha256=(
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
        existing_documents=existing_documents,
    )

    assert len(result) == 1

    comparison = result[0]

    assert comparison["existing_document_id"] == "doc-001"
    assert comparison["new_document_id"] == "doc-002"

    assert comparison["similarity"]["status"] == "same_document_updated"

    assert comparison["similarity"]["version"]["newer"] == "a" or \
           comparison["similarity"]["version"]["newer"] == "b"

    assert comparison["action"]["action"] in {
        "new_version",
        "review_required",
    }

    assert comparison["action"]["requires_review"] is True