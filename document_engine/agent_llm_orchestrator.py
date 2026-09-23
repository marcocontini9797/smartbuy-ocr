"""Provider-agnostic SmartBuy agent pipeline with deterministic validation."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from core.agent_assistant_models import AgentAnswer, AnswerStatus
from core.llm_context_models import LLMContextPack
from document_engine.agent_answer_policy import (
    classify_agent_intent,
    validate_agent_answer,
)
from document_engine.agent_prompt_builder import AgentPromptBuilder


class StructuredAgentProvider(Protocol):
    model_version: str

    def generate_agent_answer(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AgentAnswer: ...


class AgentLLMOrchestrator:
    """Retrieval -> structured context -> provider -> grounding gate."""

    version = "smartbuy-agent-orchestrator/1.0"

    def __init__(
        self,
        retriever,
        context_builder,
        provider: StructuredAgentProvider,
        prompt_builder: AgentPromptBuilder | None = None,
    ):
        self.retriever = retriever
        self.context_builder = context_builder
        self.provider = provider
        self.prompt_builder = prompt_builder or AgentPromptBuilder()

    def ask(self, property_id: int, question: str) -> AgentAnswer:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question cannot be empty")

        retrieved = self.retriever.retrieve_property_context(
            property_id,
            normalized_question,
        )
        context: LLMContextPack = self.context_builder.build(retrieved)
        available_ids = {
            source.evidence_id
            for source in context.sources
            if source.evidence_id
        }

        if not context.fact_records and not context.issue_records:
            return AgentAnswer(
                answer_id=str(uuid4()),
                property_id=property_id,
                question=normalized_question,
                intent=classify_agent_intent(normalized_question),
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                short_answer=(
                    "Nel fascicolo non ci sono informazioni sufficienti "
                    "per rispondere in modo verificabile."
                ),
                missing_information=[
                    "Occorre acquisire o analizzare i documenti pertinenti."
                ],
                follow_up_questions=[
                    "Vuoi vedere quali documenti servono per completare questa verifica?"
                ],
                metadata={
                    "orchestrator_version": self.version,
                    "prompt_version": self.prompt_builder.version,
                    "retrieval": context.metadata.get("retrieval", {}),
                    "provider_called": False,
                },
            )

        prompt = self.prompt_builder.build(normalized_question, context)
        answer = self.provider.generate_agent_answer(
            system_prompt=str(prompt["system"]),
            user_prompt=str(prompt["user"]),
        )

        if answer.property_id != property_id:
            raise ValueError("LLM response property_id does not match the request")
        if answer.question != normalized_question:
            raise ValueError("LLM response question does not match the request")

        answer.metadata.update({
            "orchestrator_version": self.version,
            "prompt_version": self.prompt_builder.version,
            "model_version": self.provider.model_version,
            "retrieval": context.metadata.get("retrieval", {}),
            "provider_called": True,
        })
        return validate_agent_answer(answer, available_ids)
