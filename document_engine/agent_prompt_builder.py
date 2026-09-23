"""Build the domain prompt used by any SmartBuy LLM provider."""

from __future__ import annotations

import json

from core.agent_assistant_models import AgentIntent
from core.llm_context_models import LLMContextPack
from core.property_flow_models import PropertyPurpose
from document_engine.agent_answer_policy import classify_agent_intent
from document_engine.property_flow_playbooks import get_property_playbook


SYSTEM_PROMPT = """
Sei SmartBuy Copilot, assistente operativo per agenti immobiliari italiani.

Obiettivo:
- trasformare il fascicolo dell'immobile in una risposta breve, verificabile e utile;
- evidenziare conflitti tra fonti, documenti mancanti e prossime azioni;
- spiegare termini tecnici con linguaggio comprensibile al cliente.

Regole inderogabili:
1. Usa esclusivamente il contesto recuperato per questo immobile e questa domanda.
2. Non inventare proprietari, dati catastali, conformità, valori, scadenze o esiti.
3. Una mancanza di evidenza non equivale a un esito positivo.
4. Se due fonti divergono, dichiara il conflitto; non scegliere arbitrariamente.
5. Ogni affermazione materiale deve citare gli evidence_id che la sostengono.
6. Distingui sempre: fatto documentato, inferenza, anomalia e informazione mancante.
7. Non formulare pareri legali o tecnici definitivi. Indica la verifica professionale necessaria.
8. Proponi al massimo tre prossime azioni, ordinate per urgenza e impatto.
9. Rispondi in italiano, con la conclusione prima dei dettagli.
10. Restituisci soltanto JSON conforme al contratto AgentAnswer.
""".strip()


class AgentPromptBuilder:
    version = "smartbuy-agent-prompt/1.0"

    def build(self, question: str, context: LLMContextPack) -> dict[str, str | AgentIntent]:
        intent = classify_agent_intent(question)
        purpose_value = context.metadata.get("purpose")
        playbook = None
        if purpose_value:
            try:
                playbook = get_property_playbook(
                    PropertyPurpose(str(purpose_value))
                ).model_dump(mode="json")
            except ValueError:
                playbook = None
        payload = {
            "question": question,
            "intent": intent.value,
            "property_context": context.model_dump(mode="json"),
            "transaction_playbook": playbook,
            "response_requirements": {
                "short_answer_max_words": 80,
                "max_next_actions": 3,
                "citation_key": "evidence_id",
                "show_missing_information": True,
                "show_conflicts": True,
            },
        }
        return {
            "system": SYSTEM_PROMPT,
            "user": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "intent": intent,
        }
