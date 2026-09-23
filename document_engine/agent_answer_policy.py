"""Deterministic safety and quality policy for SmartBuy LLM answers."""

from __future__ import annotations

from collections.abc import Iterable

from core.agent_assistant_models import (
    AgentAnswer,
    AgentIntent,
    AnswerStatus,
)


INTENT_KEYWORDS: tuple[tuple[AgentIntent, tuple[str, ...]], ...] = (
    (AgentIntent.OWNERSHIP_CHECK, ("propriet", "intestat", "venditore", "titolar")),
    (AgentIntent.CADASTRAL_CHECK, ("catast", "visura", "planimetr", "foglio", "particella", "subalterno")),
    (AgentIntent.URBANISTIC_CHECK, ("urban", "abuso", "conform", "cila", "scia", "sanatoria")),
    (AgentIntent.ENERGY_CHECK, ("ape", "energet", "epgl")),
    (AgentIntent.ENCUMBRANCE_CHECK, ("ipotec", "vincol", "gravame", "pregiudizievole")),
    (AgentIntent.DOCUMENT_GAP, ("manca", "document", "integrare", "incomplet")),
    (AgentIntent.NEXT_ACTION, ("cosa devo fare", "prossim", "azione", "come proced")),
    (AgentIntent.CLIENT_EXPLANATION, ("spiega", "cliente", "compratore", "venditore")),
)


def classify_agent_intent(question: str) -> AgentIntent:
    normalized = question.casefold().strip()
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return intent
    return AgentIntent.PROPERTY_OVERVIEW


def calculate_grounding_confidence(
    *,
    claim_evidence_ids: Iterable[Iterable[str]],
    available_evidence_ids: set[str],
    has_conflicts: bool,
    missing_information_count: int,
) -> float:
    claims = [set(ids) for ids in claim_evidence_ids]
    if not claims:
        return 0.0
    grounded = sum(bool(ids & available_evidence_ids) for ids in claims)
    coverage = grounded / len(claims)
    conflict_penalty = 0.20 if has_conflicts else 0
    missing_penalty = min(0.30, missing_information_count * 0.05)
    return round(max(0.0, min(1.0, coverage - conflict_penalty - missing_penalty)), 2)


def validate_agent_answer(answer: AgentAnswer, available_evidence_ids: set[str]) -> AgentAnswer:
    """Downgrade unsupported output instead of trusting the language model."""

    cited = {citation.evidence_id for citation in answer.citations}
    unknown = cited - available_evidence_ids
    if unknown:
        raise ValueError(f"LLM cited evidence outside retrieved context: {sorted(unknown)}")

    for claim in answer.claims:
        unknown_claim_sources = set(claim.evidence_ids) - available_evidence_ids
        if unknown_claim_sources:
            raise ValueError(
                f"Claim {claim.claim_id} cites unavailable evidence: "
                f"{sorted(unknown_claim_sources)}"
            )

    confidence = calculate_grounding_confidence(
        claim_evidence_ids=(claim.evidence_ids for claim in answer.claims),
        available_evidence_ids=available_evidence_ids,
        has_conflicts=bool(answer.conflicts),
        missing_information_count=len(answer.missing_information),
    )
    answer.confidence = confidence

    if answer.conflicts:
        answer.status = AnswerStatus.CONFLICTED
    elif not answer.claims or confidence == 0:
        answer.status = AnswerStatus.INSUFFICIENT_EVIDENCE
    elif answer.missing_information or confidence < 1:
        answer.status = AnswerStatus.PARTIAL
    else:
        answer.status = AnswerStatus.SUPPORTED
    return answer

