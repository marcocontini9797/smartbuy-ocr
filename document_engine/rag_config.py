"""The retrieval parameters the system is allowed to tune by itself, and where they live.

Only the relevance gate is learnable: it is what decides between answering and saying "not in the
documents", it can be replayed exactly from what a trace stores, and a bad value is visible
immediately. Every parameter has hard bounds; the learning loop can never leave them, whatever the
feedback says. The active version is a row of `rag_configs`; no row or any error means defaults.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from typing import Any

from document_engine.rag_search import (
    STRONG_RELEVANCE, STRONG_SIMILARITY, WEAK_RELEVANCE, WEAK_SIMILARITY, RetrievalConfig,
)


@dataclass(frozen=True)
class RagParams:
    weak_relevance: float = WEAK_RELEVANCE
    strong_relevance: float = STRONG_RELEVANCE
    weak_similarity: float = WEAK_SIMILARITY
    strong_similarity: float = STRONG_SIMILARITY


# (low, high) hard limits, and the largest move one learning cycle may make.
BOUNDS = {
    "weak_relevance": (0.50, 0.80),
    "strong_relevance": (0.75, 0.95),
    "weak_similarity": (0.20, 0.40),
    "strong_similarity": (0.35, 0.60),
}
MAX_STEP = {"weak_relevance": 0.05, "strong_relevance": 0.05, "weak_similarity": 0.03, "strong_similarity": 0.03}


def clamp(params: RagParams) -> RagParams:
    """Inside the bounds, and strong never below weak."""
    values = {k: min(max(getattr(params, k), lo), hi) for k, (lo, hi) in BOUNDS.items()}
    values["strong_relevance"] = max(values["strong_relevance"], values["weak_relevance"] + 0.05)
    values["strong_similarity"] = max(values["strong_similarity"], values["weak_similarity"] + 0.05)
    return RagParams(**values)


def step_limited(current: RagParams, wanted: RagParams) -> RagParams:
    """Move from `current` towards `wanted` by at most MAX_STEP per parameter, then clamp."""
    values = {}
    for key, limit in MAX_STEP.items():
        delta = getattr(wanted, key) - getattr(current, key)
        values[key] = getattr(current, key) + max(-limit, min(limit, delta))
    return clamp(RagParams(**values))


def from_dict(raw: dict[str, Any] | None) -> RagParams:
    known = {k: float(v) for k, v in (raw or {}).items() if k in BOUNDS and isinstance(v, (int, float))}
    return clamp(replace(RagParams(), **known))


def to_dict(params: RagParams) -> dict[str, float]:
    return {k: round(v, 3) for k, v in asdict(params).items()}


def to_retrieval_config(params: RagParams) -> RetrievalConfig:
    return replace(RetrievalConfig(), **asdict(params))


_CACHE: dict[str, Any] = {"at": 0.0, "value": (None, RagParams())}
_TTL_SECONDS = 300


def load_active(client) -> tuple[int | None, RagParams]:
    """(version, parameters) of the active configuration, cached for a few minutes. A rollback or a
    promotion therefore reaches every server within _TTL_SECONDS."""
    if time.time() - _CACHE["at"] < _TTL_SECONDS:
        return _CACHE["value"]
    try:
        rows = client.table("rag_configs").select("id,params").eq("status", "active").limit(1).execute().data or []
        value = (int(rows[0]["id"]), from_dict(rows[0]["params"])) if rows else (None, RagParams())
    except Exception:
        value = (None, RagParams())
    _CACHE.update(at=time.time(), value=value)
    return value


def invalidate_cache() -> None:
    _CACHE["at"] = 0.0
