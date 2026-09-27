"""Real LLM gateway for the SmartBuyAgentService (document_engine/agent_service.py).

Shipped with only a mock (test_agent_service.py). Built on the same
structured_call primitive extraction.py already uses in production, so this
introduces no new call pattern to the LLM provider — same client, same retry
behaviour, same MODEL/LIGHT_MODEL env-var configuration.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from llm_client import MODEL, structured_call

_CITATION_RE = re.compile(r"\(fonte:\s*([^,()]+?)(?:,\s*pag\.\s*(\d+))?\)")

SYSTEM_PROMPT = """Rispondi a domande di due diligence immobiliare su UN SOLO fascicolo, usando \
ESCLUSIVAMENTE i fatti, i rischi e i brani di documento (evidence) forniti nel messaggio dell'utente.

Regole non negoziabili:
- Non inventare mai un dato che non è nei fatti/evidence forniti. Se l'informazione richiesta non \
c'è, dillo esplicitamente ("Non risulta dai documenti caricati finora...") invece di indovinare.
- Quando affermi qualcosa che proviene da un'evidence, cita la fonte tra parentesi usando ESATTAMENTE \
il valore del campo "fonte" del brano che hai usato, copiato senza modificarlo: (fonte: {valore \
esatto del campo fonte}, pag. X) se la pagina è nota, altrimenti (fonte: {valore esatto}). Non \
sostituirlo con il tipo di documento che pensi sia (es. non scrivere "visura catastale" se il \
campo fonte del brano dice "APE_test.pdf": copia sempre il nome del file così com'è).
- Non dare consigli legali definitivi: per questioni che richiedono un parere professionale, indica \
di rivolgersi al notaio o a un tecnico.
- Rispondi in italiano, in modo diretto e conciso (massimo 4-5 frasi), senza premesse superflue.
"""


class _AgentLLMOutput(BaseModel):
    answer: str = Field(description="Risposta diretta alla domanda, con citazioni delle fonti tra parentesi dove pertinente")
    grounded: bool = Field(description="True se la risposta si basa esclusivamente sui fatti/evidence forniti, "
                                       "False se l'informazione richiesta non è presente in essi")
    confidence: float = Field(ge=0.0, le=1.0, description="Quanto la risposta è supportata dai dati forniti")


class _Response:
    def __init__(self, answer: str, confidence: float, grounded: bool, sources: list[dict[str, Any]] | None = None):
        self.answer = answer
        self.confidence = confidence
        self.metadata = {"grounded": grounded}
        self.sources = sources or []


def _cited_sources(answer: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sources the answer actually cites — via its "(fonte: X, pag. Y)"
    markers — in citation order, deduped. Distinct from `evidence` itself
    (every passage the LLM was given, whether or not it ended up using it):
    showing all of those as "sources" would badge the answer with documents
    it never actually referenced."""
    by_document: dict[str, dict[str, Any]] = {}
    for item in evidence:
        document = item.get("document")
        if document:
            by_document.setdefault(str(document).strip(), item)
    seen: set[tuple[str, Any]] = set()
    sources: list[dict[str, Any]] = []
    for raw_document, raw_page in _CITATION_RE.findall(answer):
        document = raw_document.strip()
        match = by_document.get(document)
        page = int(raw_page) if raw_page else (match.get("page") if match else None)
        key = (document, page)
        if key in seen:
            continue
        seen.add(key)
        sources.append({"document": document, "page": page})
    return sources


class AgentLLMGateway:
    def complete(self, *, task: str, context: dict[str, Any], property_id: int, user_query: str) -> _Response:
        payload = {
            "domanda": user_query,
            "fatti_del_fascicolo": context.get("facts", []),
            "rischi_rilevati": context.get("issues", []),
            "brani_di_documenti": [
                {"fonte": e.get("document"), "pagina": e.get("page"), "testo": e.get("text")}
                for e in context.get("evidence", [])
            ],
        }
        if not payload["fatti_del_fascicolo"] and not payload["brani_di_documenti"]:
            return _Response(
                "Non ho ancora nessun documento analizzato per questo fascicolo: carica almeno un documento "
                "prima di farmi domande sul suo contenuto.",
                confidence=1.0, grounded=True,
            )
        result = structured_call(
            system=SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            output_model=_AgentLLMOutput,
            model=MODEL,
        )
        sources = _cited_sources(result.answer, context.get("evidence", []))
        return _Response(result.answer, result.confidence, result.grounded, sources)
