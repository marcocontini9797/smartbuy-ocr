"""
Client OpenAI centralizzato.

Tutte le chiamate all'API passano da qui, così il resto del codice (extraction.py,
rag.py) non conosce i dettagli dell'SDK OpenAI.

Due funzioni chiave:
- structured_call(...): usa la Responses API con `text_format=<ModelloPydantic>`
  (client.responses.parse), che genera automaticamente uno schema JSON "strict"
  dal modello Pydantic e valida la risposta, restituendo direttamente un'istanza
  del modello. Niente parsing manuale di JSON, niente rischio di schema
  malformato passato a mano.
- embed_texts(...): embeddings OpenAI per la parte semantica del RAG.

Modelli configurabili via variabili d'ambiente (i nomi dei modelli OpenAI
cambiano nel tempo, quindi non li fissiamo nel codice senza possibilità di
override). Split in due livelli per bilanciare precisione e costo:
- OPENAI_MODEL (default: gpt-6-astra, il modello di punta OpenAI): usato per
  estrazione, verifica e generazione della risposta RAG finale, cioè i
  passaggi dove un errore arriva davvero all'utente e ha un costo (una cifra
  sbagliata in un atto, una risposta di due diligence non accurata).
- OPENAI_LIGHT_MODEL (default: gpt-5.6-luna): usato per compiti più semplici
  a minor impatto (classificazione del tipo di documento, reranking dei
  chunk) dove un modello più economico offre un compromesso ragionevole.
- OPENAI_EMBEDDING_MODEL (default: text-embedding-3-large): resta la scelta
  migliore nella famiglia di embedding OpenAI attuale (nessun modello più
  recente disponibile al momento).
"""

from __future__ import annotations

import os
from typing import TypeVar

import numpy as np
from pydantic import BaseModel

MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-astra")
LIGHT_MODEL = os.environ.get("OPENAI_LIGHT_MODEL", "gpt-5.6-luna")
EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

T = TypeVar("T", bound=BaseModel)

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from openai import OpenAI
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Il pacchetto 'openai' non è installato. Esegui: pip install openai"
        ) from e

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY non configurata. Impostala come variabile d'ambiente "
            "per usare classificazione/estrazione/verifica/RAG dal vivo."
        )
    _client = OpenAI(api_key=api_key)
    return _client


# Modelli che rifiutano il parametro `temperature` (es. modelli di reasoning):
# scoperti alla prima risposta 400 e poi chiamati senza.
_NO_TEMPERATURE_MODELS: set[str] = set()


def _call_with_optional_temperature(method, *, model: str, temperature: float, **kwargs):
    if model not in _NO_TEMPERATURE_MODELS:
        try:
            return method(model=model, temperature=temperature, **kwargs)
        except Exception as exc:
            if getattr(exc, "param", None) != "temperature" and "temperature" not in str(exc):
                raise
            _NO_TEMPERATURE_MODELS.add(model)
    return method(model=model, **kwargs)


def structured_call(
    *,
    system: str,
    user: str,
    output_model: type[T],
    temperature: float = 0.0,
    model: str | None = None,
) -> T:
    """Chiama il modello forzando l'output a rispettare `output_model` (Pydantic).

    temperature=0 di default: per estrazione/classificazione/verifica vogliamo
    determinismo, non creatività. Alza la temperatura solo se stai facendo
    campionamenti multipli per self-consistency (vedi extraction.py).
    I modelli che non accettano `temperature` vengono richiamati senza.
    """
    client = get_client()
    response = _call_with_optional_temperature(
        client.responses.parse,
        model=model or MODEL,
        temperature=temperature,
        instructions=system,
        input=user,
        text_format=output_model,
    )
    parsed = response.output_parsed
    if parsed is None:
        # Puo' succedere se il modello rifiuta la richiesta o la risposta non
        # rispetta lo schema in modo irrecuperabile: meglio fallire in modo
        # esplicito che propagare un None silenzioso.
        raise RuntimeError(
            f"Il modello non ha prodotto un output strutturato valido. "
            f"Risposta grezza: {getattr(response, 'output_text', '<vuota>')}"
        )
    return parsed


def free_text_call(*, system: str, user: str, temperature: float = 0.2, model: str | None = None) -> str:
    """Chiamata a testo libero (usata per la generazione della risposta RAG finale)."""
    client = get_client()
    response = _call_with_optional_temperature(
        client.responses.create,
        model=model or MODEL,
        temperature=temperature,
        instructions=system,
        input=user,
    )
    return response.output_text


def embed_texts(texts: list[str], model: str | None = None) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0))
    client = get_client()
    response = client.embeddings.create(model=model or EMBEDDING_MODEL, input=texts)
    return np.array([d.embedding for d in response.data])


