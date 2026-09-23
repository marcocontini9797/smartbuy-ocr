from core.agent_assistant_models import (
    AgentAnswer,
    AgentIntent,
    AnswerStatus,
    ClaimCitation,
    SupportedClaim,
)
from document_engine.agent_answer_policy import (
    calculate_grounding_confidence,
    classify_agent_intent,
    validate_agent_answer,
)


def test_real_estate_intents_are_deterministic():
    assert classify_agent_intent("Chi è il proprietario?") == AgentIntent.OWNERSHIP_CHECK
    assert classify_agent_intent("La planimetria è conforme?") == AgentIntent.CADASTRAL_CHECK
    assert classify_agent_intent("Cosa devo fare adesso?") == AgentIntent.NEXT_ACTION


def test_confidence_measures_claim_coverage_and_penalizes_conflicts():
    score = calculate_grounding_confidence(
        claim_evidence_ids=[["EV-1"], []],
        available_evidence_ids={"EV-1"},
        has_conflicts=True,
        missing_information_count=1,
    )
    assert score == 0.25


def test_answer_is_downgraded_when_information_is_missing():
    answer = AgentAnswer(
        answer_id="ANS-1",
        property_id=16,
        question="Chi è il proprietario?",
        intent=AgentIntent.OWNERSHIP_CHECK,
        status=AnswerStatus.SUPPORTED,
        short_answer="La visura indica Mario Rossi, ma manca l'atto aggiornato.",
        claims=[
            SupportedClaim(
                claim_id="CL-1",
                statement="La visura indica Mario Rossi.",
                status=AnswerStatus.SUPPORTED,
                evidence_ids=["EV-1"],
            )
        ],
        citations=[
            ClaimCitation(
                evidence_id="EV-1",
                document_name="Visura catastale",
                page=1,
            )
        ],
        missing_information=["Atto di provenienza aggiornato"],
    )

    checked = validate_agent_answer(answer, {"EV-1"})
    assert checked.status == AnswerStatus.PARTIAL
    assert checked.confidence == 0.95


def test_hallucinated_citation_is_rejected():
    answer = AgentAnswer(
        answer_id="ANS-2",
        property_id=16,
        question="Ci sono ipoteche?",
        intent=AgentIntent.ENCUMBRANCE_CHECK,
        status=AnswerStatus.SUPPORTED,
        short_answer="Non risultano ipoteche.",
        claims=[
            SupportedClaim(
                claim_id="CL-2",
                statement="Non risultano ipoteche.",
                status=AnswerStatus.SUPPORTED,
                evidence_ids=["EV-INVENTED"],
            )
        ],
    )

    try:
        validate_agent_answer(answer, {"EV-REAL"})
    except ValueError as exc:
        assert "outside" in str(exc) or "unavailable" in str(exc)
    else:
        raise AssertionError("An unavailable evidence id must be rejected")
