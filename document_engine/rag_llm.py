"""The language-model steps of retrieval: rephrasing a short question and reranking candidates.

Both are optional and fail soft (no key, rate limit, malformed answer: they return
nothing and retrieval goes on without them). They use the light model, like
classification: judging whether a passage answers a question is a simpler task than
writing the answer.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from llm_client import LIGHT_MODEL, structured_call

_RERANK_CHARS = 700


class _Rephrasings(BaseModel):
    riformulazioni: list[str] = Field(description="Riformulazioni della domanda, stesso significato, parole diverse")


class _Judgement(BaseModel):
    indice: int
    rilevanza: float = Field(ge=0.0, le=1.0)


class _Judgements(BaseModel):
    giudizi: list[_Judgement]


def _available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def expand_question(question: str, n: int = 3) -> list[str]:
    """Alternative phrasings of a short question, for passages that word the same thing
    differently ("posso tenere un cane?" / "animali domestici")."""
    if not _available():
        return []
    try:
        result = structured_call(
            system=("Riformuli domande su documenti immobiliari italiani per migliorare la ricerca. Mantieni "
                    "ESATTAMENTE lo stesso significato, senza aggiungere né togliere informazioni: usa parole "
                    "diverse, sinonimi e i termini tecnici o giuridici con cui un documento direbbe la stessa cosa."),
            user=f"Domanda: {question}\n\nScrivi {n} riformulazioni.", output_model=_Rephrasings,
            temperature=0.2, model=LIGHT_MODEL)
        return [q.strip() for q in result.riformulazioni if q.strip()][:n]
    except Exception:
        return []


def rerank_passages(question: str, passages) -> dict[int, float]:
    """Relevance 0..1 of each candidate passage (by position in the list)."""
    if not _available() or not passages:
        return {}
    listing = "\n\n".join(
        f"[{i}] {p.context}\n{p.text[:_RERANK_CHARS]}" for i, p in enumerate(passages))
    try:
        result = structured_call(
            system=("Giudichi quanto ciascun passaggio di un fascicolo immobiliare serve a rispondere a una domanda. "
                    "Rilevanza alta (0.8-1.0) SOLO se il passaggio contiene la risposta; media (0.3-0.6) se tratta "
                    "l'argomento ma non risponde; 0 se è fuori tema. Un passaggio che parla di una cosa simile ma di "
                    "un altro documento, anno o unità non risponde. Includi tutti gli indici."),
            user=f"Domanda: {question}\n\nPassaggi:\n\n{listing}", output_model=_Judgements,
            temperature=0.0, model=LIGHT_MODEL)
        return {j.indice: j.rilevanza for j in result.giudizi if 0 <= j.indice < len(passages)}
    except Exception:
        return {}


class _Support(BaseModel):
    supportata: bool = Field(description="True se OGNI affermazione della risposta è presente nei brani")


def judge_support(question: str, answer: str, passages: list[str]) -> bool | None:
    """Independent check used to vet human ratings: is the answer fully supported by the passages it
    was given? None when it cannot tell (no key, no passages, error)."""
    if not _available() or not passages:
        return None
    listing = "\n\n".join(f"[{i}] {text[:1200]}" for i, text in enumerate(passages))
    try:
        result = structured_call(
            system=("Verifichi se una risposta a una domanda su un fascicolo immobiliare è SUPPORTATA dai brani "
                    "forniti. Supportata = ogni dato e affermazione della risposta si trova nei brani. Se la risposta "
                    "dice che l'informazione non risulta, è supportata solo se i brani davvero non la contengono. "
                    "Se aggiunge, cambia o inventa qualcosa, non è supportata."),
            user=f"Domanda: {question}\n\nRisposta: {answer}\n\nBrani:\n\n{listing}",
            output_model=_Support, temperature=0.0, model=LIGHT_MODEL)
        return result.supportata
    except Exception:
        return None
