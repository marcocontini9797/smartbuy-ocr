"""Measure retrieval quality: the prototype RAG against the new retrieval.

Both run on the synthetic fascicolo in evaluation/rag_corpus.py, without any
language-model call (query expansion and reranking are left out for both, so the
comparison is of the retrieval itself). Embeddings are real OpenAI ones with
`--live` (cached on disk, a few thousand tokens in total) or a hashing embedder
offline, which only checks the mechanics, not semantic quality.

    .venv\\Scripts\\python.exe -m evaluation.evaluate_rag --live
    .venv\\Scripts\\python.exe -m evaluation.evaluate_rag --live --sweep

"prototype" is the retrieval of the original smartbuy_due_diligence/rag.py: fixed
800/150 structure-or-window chunks, TF-IDF + embeddings fused by RRF (k=10), top 5,
and no way to say "nothing relevant". Its TF-IDF is fitted on the whole corpus,
the most favourable case for it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from document_engine.rag_index import build_chunk_rows, embed_in_batches
from document_engine.rag_search import EMBED_DIMENSIONS, RetrievalConfig, retrieve
from document_engine.rag_store import MemoryChunkStore

ROOT = Path(__file__).parent
CACHE = ROOT / ".cache" / "embeddings.json"
REPORTS = ROOT / "reports"
PROPERTY_ID = 1


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


# --- embedders ---------------------------------------------------------------------------------

def hashing_embedder(dimensions: int = 512):
    """Offline stand-in: hashed words and character trigrams. Checks the mechanics only."""
    def embed(texts):
        out = np.zeros((len(texts), dimensions))
        for row, text in enumerate(texts):
            words = re.findall(r"\w+", norm(text))
            grams = [w[i:i + 3] for w in words for i in range(max(len(w) - 2, 1))]
            for token in words + grams:
                out[row, int(hashlib.md5(token.encode()).hexdigest(), 16) % dimensions] += 1
        return out
    return embed


def live_embedder(dimensions: int = EMBED_DIMENSIONS):
    from dotenv import load_dotenv
    from llm_client import EMBEDDING_MODEL, embed_texts

    load_dotenv()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    stats = {"calls": 0, "texts": 0, "chars": 0}

    def embed(texts):
        keys = [hashlib.sha256(f"{EMBEDDING_MODEL}|{dimensions}|{t}".encode()).hexdigest() for t in texts]
        missing = [i for i, k in enumerate(keys) if k not in cache]
        if missing:
            stats["calls"] += 1
            stats["texts"] += len(missing)
            stats["chars"] += sum(len(texts[i]) for i in missing)
            for i, vector in zip(missing, embed_texts([texts[i] for i in missing], dimensions=dimensions)):
                cache[keys[i]] = vector.tolist()
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache), encoding="utf-8")
        return np.array([cache[k] for k in keys])

    embed.stats = stats                                        # type: ignore[attr-defined]
    return embed


# --- the prototype's retrieval (smartbuy_due_diligence/rag.py), reproduced ------------------------

_PROTO_STRUCTURE = re.compile(r"(?=\b(?:Art(?:icolo)?\.?\s*\d+[a-z]?\b|\n\s*\d{1,2}\)\s|\n\s*\d{1,2}\.\d\s))", re.IGNORECASE)


def _proto_window(text, size, overlap):
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def proto_chunks(text, size=800, overlap=150):
    text = re.sub(r"[ \t]+", " ", text).strip()
    segments = [s.strip() for s in _PROTO_STRUCTURE.split(text) if s.strip()]
    if len(segments) <= 1:
        return _proto_window(text, size, overlap)
    chunks = []
    for segment in segments:
        chunks.extend(_proto_window(segment, size, overlap) if len(segment) > int(size * 1.5) else [segment])
    return chunks


class Tfidf:
    """scikit-learn TfidfVectorizer defaults (lowercase, \\w\\w+ tokens, smooth idf, l2)."""

    def __init__(self, corpus):
        self.vocab = {}
        docs = [re.findall(r"(?u)\b\w\w+\b", c.lower()) for c in corpus]
        for tokens in docs:
            for t in set(tokens):
                self.vocab.setdefault(t, len(self.vocab))
        df = Counter(t for tokens in docs for t in set(tokens))
        self.idf = np.zeros(len(self.vocab))
        for t, i in self.vocab.items():
            self.idf[i] = math.log((1 + len(docs)) / (1 + df[t])) + 1

    def transform(self, texts):
        out = np.zeros((len(texts), len(self.vocab)))
        for row, text in enumerate(texts):
            for t, n in Counter(re.findall(r"(?u)\b\w\w+\b", text.lower())).items():
                if t in self.vocab:
                    out[row, self.vocab[t]] = n * self.idf[self.vocab[t]]
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


def _ranks(scores):
    order = np.argsort(-scores)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(len(order))
    return ranks


class PrototypeRetriever:
    """The prototype's fusion (TF-IDF + embeddings, RRF k=10, no gate) over a given list of chunk texts."""

    def __init__(self, embed, chunks):
        self.embed = embed
        self.chunks = chunks
        self.vectors = np.asarray(embed(self.chunks))
        self.tfidf = Tfidf(self.chunks)
        self.lexical = self.tfidf.transform(self.chunks)

    def search(self, question, top_k=5):
        q = np.asarray(self.embed([question])[0])
        sem = self.vectors @ q / np.where(np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(q) == 0, 1e-9,
                                          np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(q))
        lex = self.lexical @ self.tfidf.transform([question])[0]
        fused = 1.0 / (10 + _ranks(sem)) + 1.0 / (10 + _ranks(lex))
        top = np.argsort(-fused)[:top_k]
        return [self.chunks[i] for i in top], float(sem[top[0]])


# --- the new retrieval ---------------------------------------------------------------------------------

def build_store(embed, documents, *, context=True):
    store = MemoryChunkStore()
    for doc in documents:
        rows = build_chunk_rows(document_type=doc["type"], file_name=doc["name"], full_text=doc["text"])
        if not context:
            rows = [type(r)(r.chunk_index, r.page_start, r.page_end, r.heading, r.content, "") for r in rows]
        vectors = embed_in_batches(embed, [r.embedding_text for r in rows])
        for row, vector in zip(rows, vectors):
            store.add(property_id=PROPERTY_ID, document_id=doc["id"], document_name=doc["name"],
                      document_type=doc["type"], chunk_index=row.chunk_index, page_start=row.page_start,
                      page_end=row.page_end, heading=row.heading, content=row.content, context=row.context,
                      embedding=vector)
    return store


# --- scoring -----------------------------------------------------------------------------------------------

def first_hit(texts, gold):
    for position, text in enumerate(texts, start=1):
        if norm(gold) in norm(text):
            return position
    return None


def summarise(rows):
    answerable = [r for r in rows if r["gold"]]
    absent = [r for r in rows if not r["gold"]]
    out = {"questions": len(rows), "answerable": len(answerable), "absent": len(absent)}
    for k in (1, 3, 5):
        out[f"recall@{k}"] = round(sum(1 for r in answerable if r["rank"] and r["rank"] <= k) / max(len(answerable), 1), 3)
    out["mrr@5"] = round(sum(1 / r["rank"] for r in answerable if r["rank"] and r["rank"] <= 5) / max(len(answerable), 1), 3)
    out["reachable_in_context"] = round(sum(1 for r in answerable if r["in_context"]) / max(len(answerable), 1), 3)
    out["avg_context_chars"] = round(sum(r["chars"] for r in rows) / len(rows))
    out["absent_refused"] = round(sum(1 for r in absent if r["refused"]) / max(len(absent), 1), 3)
    out["answerable_wrongly_refused"] = round(sum(1 for r in answerable if r["refused"]) / max(len(answerable), 1), 3)
    return out


def load_corpus(name):
    if name in ("realistic", "scale"):
        from evaluation import rag_corpus_realistic as module

        return (module.scaled_documents() if name == "scale" else module.DOCUMENTS), module.QUESTIONS
    else:
        from evaluation import rag_corpus as module
    return module.DOCUMENTS, module.QUESTIONS


def evaluate(embed, config, documents, questions, *, llm=False):
    from document_engine.rag_chunking import chunk_document

    proto = PrototypeRetriever(embed, [c for d in documents for c in proto_chunks(d["text"])])
    new_chunks = PrototypeRetriever(embed, [c.text for d in documents for c in chunk_document(d["text"])])
    plain = {"prototype": (proto, 5), "prototype_top8": (proto, 8), "new_chunks_old_retrieval": (new_chunks, 5)}
    systems = {"new": (build_store(embed, documents, context=True), {}),
               "new_without_context": (build_store(embed, documents, context=False), {})}
    if llm:
        from evaluation.llm_cache import cached_expander, cached_reranker

        store = systems["new"][0]
        systems["new+rerank"] = (store, {"rerank": cached_reranker()})
        systems["new+rerank+expand"] = (store, {"rerank": cached_reranker(), "expand": cached_expander()})
    results = defaultdict(list)
    for qid, category, question, gold in questions:
        for name, (retriever, top_k) in plain.items():
            chunks, best = retriever.search(question, top_k)
            results[name].append({"id": qid, "category": category, "gold": gold, "similarity": best,
                                  "rank": first_hit(chunks, gold) if gold else None,
                                  "in_context": bool(gold and first_hit(chunks, gold)), "refused": False,
                                  "chars": sum(len(c) for c in chunks)})
        for name, (store, extras) in systems.items():
            r = retrieve(store, embed, PROPERTY_ID, question, config=config, **extras)
            ranked_texts = [p.text for p in r.ranked]
            context_texts = [p.text for p in r.passages]
            results[name].append({"id": qid, "category": category, "gold": gold, "similarity": r.best_similarity,
                                  "rank": first_hit(ranked_texts, gold) if gold else None,
                                  "in_context": bool(gold and first_hit(context_texts, gold)),
                                  "refused": r.strength == "none", "strength": r.strength,
                                  "relevance": r.best_relevance, "chars": sum(len(t) for t in context_texts)})
    return results


def print_report(results):
    print(f"\n{'system':<22}{'R@1':>6}{'R@3':>6}{'R@5':>6}{'MRR':>7}{'in ctx':>8}{'chars':>7}{'refuse absent':>15}{'wrong refusal':>15}")
    for name, rows in results.items():
        s = summarise(rows)
        print(f"{name:<22}{s['recall@1']:>6}{s['recall@3']:>6}{s['recall@5']:>6}{s['mrr@5']:>7}"
              f"{s['reachable_in_context']:>8}{s['avg_context_chars']:>7}{s['absent_refused']:>15}{s['answerable_wrongly_refused']:>15}")
    print("\nrecall@5 by category")
    categories = sorted({r["category"] for r in next(iter(results.values())) if r["gold"]})
    print(f"{'system':<22}" + "".join(f"{c:>12}" for c in categories))
    for name, rows in results.items():
        cells = []
        for c in categories:
            subset = [r for r in rows if r["category"] == c and r["gold"]]
            cells.append(f"{sum(1 for r in subset if r['rank'] and r['rank'] <= 5) / len(subset):>12.2f}")
        print(f"{name:<22}" + "".join(cells))


def print_sweep(results):
    rows = results["new"]
    print("\nsimilarity gate (best similarity of the top 3 hits) on the new retrieval")
    print(f"{'floor':>7}{'absent refused':>16}{'answerable refused':>20}")
    for floor in (0.15, 0.2, 0.25, 0.28, 0.3, 0.32, 0.35, 0.38, 0.4, 0.45):
        absent = [r for r in rows if not r["gold"]]
        answerable = [r for r in rows if r["gold"]]
        print(f"{floor:>7}{sum(r['similarity'] < floor for r in absent) / len(absent):>16.2f}"
              f"{sum(r['similarity'] < floor for r in answerable) / len(answerable):>20.2f}")
    for label, group in (("answerable", [r for r in rows if r["gold"]]), ("absent", [r for r in rows if not r["gold"]])):
        values = sorted(r["similarity"] for r in group)
        print(f"{label}: min {values[0]:.2f}  p25 {values[len(values) // 4]:.2f}  median {values[len(values) // 2]:.2f}  max {values[-1]:.2f}")


def print_relevance_sweep(results):
    rows = results.get("new+rerank")
    if not rows:
        return
    answerable = [r for r in rows if r["gold"]]
    absent = [r for r in rows if not r["gold"]]
    print("\nrelevance gate (best model relevance of the top 3 hits) on new+rerank")
    print(f"{'floor':>7}{'absent refused':>16}{'answerable refused':>20}")
    for floor in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        print(f"{floor:>7}{sum((r['relevance'] or 0) < floor for r in absent) / len(absent):>16.2f}"
              f"{sum((r['relevance'] or 0) < floor for r in answerable) / len(answerable):>20.2f}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="real OpenAI embeddings (cached) instead of the offline hashing embedder")
    parser.add_argument("--corpus", choices=("base", "realistic", "scale"), default="realistic")
    parser.add_argument("--llm", action="store_true", help="also run the model steps (rephrasing, reranking; light model, cached)")
    parser.add_argument("--sweep", action="store_true", help="print the similarity-gate trade-off")
    parser.add_argument("--save", action="store_true", help="write the report to evaluation/reports/")
    args = parser.parse_args(argv)

    embed = live_embedder() if args.live else hashing_embedder()
    documents, questions = load_corpus(args.corpus)
    print(f"embeddings: {'OpenAI (live, cached)' if args.live else 'offline hashing (mechanics only)'}; corpus {args.corpus}: "
          f"{len(documents)} documents, {sum(len(d['text']) for d in documents)} characters, {len(questions)} questions")
    results = evaluate(embed, RetrievalConfig(), documents, questions, llm=args.llm)
    print_report(results)
    if args.sweep:
        print_sweep(results)
        print_relevance_sweep(results)
    if args.live:
        print(f"\nembedding calls this run: {embed.stats}")           # type: ignore[attr-defined]
    if args.save:
        REPORTS.mkdir(exist_ok=True)
        path = REPORTS / f"rag-{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps({"live": args.live, "summary": {k: summarise(v) for k, v in results.items()},
                                    "rows": results}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
