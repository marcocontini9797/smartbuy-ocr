from document_engine.fascicolo_builder import build_fascicolo_action


def test_duplicate_document():
    similarity = {
        "engine_version": "2.0",
        "status": "duplicate",
        "similarity_score": 1.0,
        "duplicate_exact": True,
        "requires_review": False,
        "automatic_merge_allowed": False,
        "reasons": [
            "matching_sha256_bytes_not_independent_evidence"
        ],
    }

    existing = {
        "document_id": "doc-001",
        "document_type": "visura_catastale",
    }

    new = {
        "document_id": "doc-002",
        "document_type": "visura_catastale",
    }

    result = build_fascicolo_action(
        new,
        existing_document=existing,
        similarity_result=similarity,
    )

    assert result["action"] == "duplicate"
    assert result["requires_review"] is False
    assert result["automatic_merge_allowed"] is False
    assert result["previous_document_id"] == "doc-001"
    assert result["new_document_id"] == "doc-002"


def test_new_document_version():
    similarity = {
        "engine_version": "2.0",
        "status": "same_document_updated",
        "similarity_score": 0.25,
        "duplicate_exact": False,
        "requires_review": True,
        "automatic_merge_allowed": False,
        "reasons": [
            "same_explicit_series_units_type_and_later_issue_date"
        ],
        "conflicts": [],
        "version": {
            "assessment": "candidate_requires_review",
            "newer": "b",
        },
        "identity": {
            "relation": "same_units",
        },
    }

    existing = {
        "document_id": "visura-2025",
        "document_type": "visura_catastale",
    }

    new = {
        "document_id": "visura-2026",
        "document_type": "visura_catastale",
    }

    result = build_fascicolo_action(
        new,
        existing_document=existing,
        similarity_result=similarity,
    )

    assert result["action"] == "new_version"
    assert result["requires_review"] is True
    assert result["automatic_merge_allowed"] is False
    assert result["previous_document_id"] == "visura-2025"
    assert result["new_document_id"] == "visura-2026"


def test_conflict_requires_review():
    similarity = {
        "engine_version": "2.0",
        "status": "possible_conflict",
        "similarity_score": 0.25,
        "duplicate_exact": False,
        "requires_review": True,
        "automatic_merge_allowed": False,
        "reasons": [
            "differences_require_cross_validation"
        ],
        "conflicts": [
            {
                "field": "ocr_numeric_tokens",
                "kind": "numeric_change_requires_reading",
            }
        ],
    }

    existing = {
        "document_id": "visura-2025",
        "document_type": "visura_catastale",
    }

    new = {
        "document_id": "visura-2026",
        "document_type": "visura_catastale",
    }

    result = build_fascicolo_action(
        new,
        existing_document=existing,
        similarity_result=similarity,
    )

    assert result["action"] == "review_conflict"
    assert result["requires_review"] is True
    assert result["automatic_merge_allowed"] is False
    assert result["previous_document_id"] == "visura-2025"


def test_different_document_is_added():
    similarity = {
        "engine_version": "2.0",
        "status": "different",
        "similarity_score": 0.0,
        "duplicate_exact": False,
        "requires_review": False,
        "automatic_merge_allowed": False,
        "reasons": [
            "different_cadastral_units"
        ],
    }

    existing = {
        "document_id": "doc-001",
        "document_type": "visura_catastale",
    }

    new = {
        "document_id": "doc-002",
        "document_type": "visura_catastale",
    }

    organization = {
        "recommended_folder": "01_Catasto",
        "recommended_name": "Visura_Catastale.pdf",
    }

    result = build_fascicolo_action(
        new,
        existing_document=existing,
        similarity_result=similarity,
        organization=organization,
    )

    assert result["action"] == "add_document"
    assert result["requires_review"] is False
    assert result["folder"] == "01_Catasto"
    assert result["recommended_name"] == "Visura_Catastale.pdf"
    assert result["new_document_id"] == "doc-002"