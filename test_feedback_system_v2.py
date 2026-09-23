from core.feedback_models import FeedbackAction, FeedbackEvent
from document_engine.feedback_service import (
    FeedbackConflictError, FeedbackService, build_signal,
)


class MemoryRepository:
    def __init__(self):
        self.target = {
            "id": "fact-1", "version": "v3",
            "payload": {"field": "energy_class", "value": "A3"},
        }
        self.calls = []

    def load_target(self, event):
        return self.target

    def ingest_atomic(self, event, signal, recalculation_stages):
        self.calls.append((event, signal, recalculation_stages))
        return {"status": "accepted"}


def correction(**updates):
    data = dict(
        idempotency_key="idem-1", tenant_id="tenant-1", property_id=16,
        actor_user_id="expert-1", target_type="FACT", target_id="fact-1",
        expected_version="v3", action="CORRECT", origin="EXPERT_REVIEW",
        original_payload={"field": "energy_class", "value": "A3"},
        corrected_payload={"field": "energy_class", "value": "A2"},
        evidence_ids=["evidence-1"], document_id="2", analysis_result_id="analysis-1",
        failure_stage="EXTRACTION", component_versions={"extractor": "2.1"},
    )
    data.update(updates)
    return FeedbackEvent(**data)


def test_correction_keeps_lineage_and_schedules_dependent_engines():
    repository = MemoryRepository()
    result = FeedbackService(repository).submit(correction(), actor_role="DOMAIN_EXPERT")
    _, signal, stages = repository.calls[0]
    assert result.status == "accepted"
    assert signal.expected_payload["value"] == "A2"
    assert signal.document_id == "2"
    assert signal.analysis_result_id == "analysis-1"
    assert signal.component_versions["extractor"] == "2.1"
    assert stages == ["cross_validation", "issues", "risk", "actions", "evaluation"]


def test_stale_version_is_rejected_before_write():
    repository = MemoryRepository()
    try:
        FeedbackService(repository).submit(correction(expected_version="v2"))
        assert False, "expected conflict"
    except FeedbackConflictError:
        assert repository.calls == []


def test_changed_snapshot_is_rejected_before_write():
    repository = MemoryRepository()
    try:
        FeedbackService(repository).submit(correction(
            original_payload={"field": "energy_class", "value": "G"}
        ))
        assert False, "expected conflict"
    except FeedbackConflictError:
        assert repository.calls == []


def test_signal_id_is_deterministic_for_same_event():
    value = correction()
    assert build_signal(value).signal_id == build_signal(value).signal_id


def test_correction_without_replacement_is_invalid():
    try:
        correction(corrected_payload=None)
        assert False, "expected validation error"
    except ValueError:
        pass
