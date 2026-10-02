"""Disk cache for the model steps of retrieval, so re-running the evaluation does not pay twice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

from document_engine.rag_llm import expand_question, rerank_passages

CACHE = Path(__file__).parent / ".cache" / "llm_steps.json"
STATS = {"expand_calls": 0, "rerank_calls": 0}


def _load() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def _store(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def cached_expander():
    load_dotenv()

    def expand(question):
        cache = _load()
        key = "expand|" + hashlib.sha256(question.encode()).hexdigest()
        if key not in cache:
            STATS["expand_calls"] += 1
            result = expand_question(question)
            if not result:                      # a failed call is not cached: the next run retries it
                return []
            cache[key] = result
            _store(cache)
        return cache[key]
    return expand


def cached_reranker():
    load_dotenv()

    def rerank(question, passages):
        cache = _load()
        key = "rerank|" + hashlib.sha256((question + "".join(p.context + p.text for p in passages)).encode()).hexdigest()
        if key not in cache:
            STATS["rerank_calls"] += 1
            result = rerank_passages(question, passages)
            if not result:
                return {}
            cache[key] = {str(i): v for i, v in result.items()}
            _store(cache)
        return {int(i): v for i, v in cache[key].items()}
    return rerank
