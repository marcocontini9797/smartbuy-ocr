"""One learning cycle of the RAG: vet new human ratings, tune the gate, adopt or roll back.

Runs with a privileged client from a scheduler (n8n, see api/ops_routes.py). Order matters:
1. roll back first, if the active configuration is performing worse than the one it replaced;
2. turn new ratings into labels (judge + user reliability, see rag_trust);
3. only if nothing was rolled back and the active configuration is old enough, let the tuner
   propose new parameters (see rag_tuner) and adopt them if every guard holds.

Everything is recorded: the configuration history (`rag_configs`, with reason and metrics) and
the verdict on every rating (`rag_feedback_labels`), so any change can be explained afterwards.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Sequence

from document_engine.rag_config import RagParams, from_dict, invalidate_cache, to_dict
from document_engine.rag_trust import UserHistory, decide_explicit, decide_implicit
from document_engine.rag_tuner import Label, propose, should_roll_back

COOLDOWN = timedelta(days=7)
BATCH = 200
Judge = Callable[[str, str, list[str]], "bool | None"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_history(feedback: dict[str, Any], by_user: Sequence[dict[str, Any]], past_labels: Sequence[dict[str, Any]]) -> UserHistory:
    """Track record of the user behind `feedback`, from their other ratings and earlier labels."""
    when = _parse(feedback["created_at"])
    before = sorted((f for f in by_user if f["id"] != feedback["id"] and _parse(f["created_at"]) < when),
                    key=lambda f: f["created_at"])
    judged = [l for l in past_labels if l.get("judge_supported") is not None]
    agreed = sum(1 for l in judged if (l["rating"] == 1) == bool(l["judge_supported"]))
    contradicts = any(f["question"].strip().casefold() == feedback["question"].strip().casefold()
                      and f["rating"] != feedback["rating"] for f in by_user if f["id"] != feedback["id"])
    return UserHistory(
        agreed=agreed, judged=len(judged),
        recent_hour=sum(1 for f in before if when - _parse(f["created_at"]) <= timedelta(hours=1)),
        recent_ratings=[f["rating"] for f in before][-10:], contradicts_self=contradicts)


def label_new_feedback(client, judge: Judge) -> dict[str, int]:
    done = {r["feedback_id"] for r in (client.table("rag_feedback_labels").select("feedback_id")
                                       .eq("source", "explicit").execute().data or [])}
    rows = (client.table("agent_answer_feedback").select("id,user_id,question,answer,rating,trace_id,created_at")
            .not_.is_("trace_id", "null").order("created_at").limit(BATCH * 3).execute().data or [])
    todo = [r for r in rows if r["id"] not in done][:BATCH]
    counts = {"accepted": 0, "review": 0, "rejected": 0}
    for fb in todo:
        trace = (client.table("agent_retrieval_traces").select("id,chunk_ids").eq("id", fb["trace_id"]).limit(1).execute().data or [])
        texts: list[str] = []
        if trace and trace[0]["chunk_ids"]:
            chunks = (client.table("document_chunks").select("content").in_("id", trace[0]["chunk_ids"]).execute().data or [])
            texts = [c["content"] for c in chunks]
        supported = judge(fb["question"], fb["answer"], texts)
        by_user = (client.table("agent_answer_feedback").select("id,question,rating,created_at")
                   .eq("user_id", fb["user_id"]).order("created_at", desc=True).limit(300).execute().data or [])
        past = (client.table("rag_feedback_labels").select("rating,judge_supported").eq("user_id", fb["user_id"])
                .eq("source", "explicit").limit(500).execute().data or [])
        decision = decide_explicit(fb["rating"], supported, build_history(fb, by_user, past))
        client.table("rag_feedback_labels").upsert({
            "trace_id": fb["trace_id"], "feedback_id": fb["id"], "source": "explicit", "user_id": fb["user_id"],
            "rating": fb["rating"], "weight": round(decision.weight, 4), "verdict": decision.verdict,
            "judge_supported": supported, "reasons": decision.reasons}, on_conflict="trace_id,source").execute()
        counts[decision.verdict] += 1
    return counts


REASK_WINDOW = timedelta(seconds=180)
REASK_SIMILARITY = 0.85


def _vector(value) -> list[float] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return [float(x) for x in value] if value else None


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


def find_reasks(traces: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Traces whose answer the same user, in the same fascicolo, asked again within minutes: the
    earlier trace of each pair. Pure: `traces` need id, user_id, property_id, created_at, question_embedding."""
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for t in traces:
        groups.setdefault((t["user_id"], t["property_id"]), []).append(t)
    found = []
    for group in groups.values():
        group.sort(key=lambda t: t["created_at"])
        for first, second in zip(group, group[1:]):
            a, b = _vector(first.get("question_embedding")), _vector(second.get("question_embedding"))
            if a and b and _parse(second["created_at"]) - _parse(first["created_at"]) <= REASK_WINDOW \
                    and _cosine(a, b) >= REASK_SIMILARITY:
                found.append(first)
    return found


def label_reasks(client, judge: Judge) -> dict[str, int]:
    since = (_now() - timedelta(days=14)).isoformat()
    traces = (client.table("agent_retrieval_traces")
              .select("id,user_id,property_id,created_at,question,question_embedding,answer,chunk_ids")
              .gte("created_at", since).not_.is_("answer", "null").limit(2000).execute().data or [])
    labelled = {r["trace_id"] for r in (client.table("rag_feedback_labels").select("trace_id").limit(5000).execute().data or [])}
    counts = {"accepted": 0, "review": 0, "rejected": 0}
    for trace in find_reasks(traces):
        if trace["id"] in labelled:        # a person already rated it, or it was labelled before
            continue
        texts: list[str] = []
        if trace["chunk_ids"]:
            texts = [c["content"] for c in (client.table("document_chunks").select("content")
                                            .in_("id", trace["chunk_ids"]).execute().data or [])]
        decision = decide_implicit(judge(trace["question"], trace["answer"], texts))
        client.table("rag_feedback_labels").upsert({
            "trace_id": trace["id"], "source": "implicit_reask", "user_id": trace["user_id"], "rating": -1,
            "weight": decision.weight, "verdict": decision.verdict,
            "judge_supported": False if decision.verdict == "accepted" else None,
            "reasons": decision.reasons}, on_conflict="trace_id,source").execute()
        counts[decision.verdict] += 1
    return counts


def _accepted_labels(client) -> list[tuple[Label, int | None]]:
    rows = (client.table("rag_feedback_labels").select("trace_id,user_id,rating,weight,judge_supported")
            .eq("verdict", "accepted").limit(5000).execute().data or [])
    if not rows:
        return []
    traces = {}
    ids = [r["trace_id"] for r in rows]
    for start in range(0, len(ids), 200):
        for t in (client.table("agent_retrieval_traces")
                  .select("id,strength,best_similarity,candidates,identifier_hit,config_version")
                  .in_("id", ids[start:start + 200]).execute().data or []):
            traces[t["id"]] = t
    out = []
    for r in rows:
        t = traces.get(r["trace_id"])
        if not t or r["weight"] <= 0:
            continue
        # a 👎 only teaches the gate when the judge also found the answer unsupported
        if r["rating"] == -1 and r["judge_supported"] is not False:
            continue
        out.append((Label(kind="good" if r["rating"] == 1 else "bad", weight=float(r["weight"]), user_id=r["user_id"],
                          strength=t["strength"], identifier_hit=bool(t["identifier_hit"]),
                          candidates=t["candidates"] or [], best_similarity=float(t["best_similarity"] or 0.0)),
                    t.get("config_version")))
    return out


def _active(client) -> dict[str, Any] | None:
    rows = client.table("rag_configs").select("*").eq("status", "active").limit(1).execute().data or []
    return rows[0] if rows else None


def _roll_back_if_worse(client, active: dict[str, Any]) -> str | None:
    if not active.get("parent_id"):
        return None
    rows = (client.table("rag_feedback_labels").select("trace_id,rating").eq("verdict", "accepted")
            .eq("source", "explicit").limit(5000).execute().data or [])
    versions = {}
    ids = [r["trace_id"] for r in rows]
    for start in range(0, len(ids), 200):
        for t in (client.table("agent_retrieval_traces").select("id,config_version")
                  .in_("id", ids[start:start + 200]).execute().data or []):
            versions[t["id"]] = t["config_version"]
    new = [r["rating"] for r in rows if versions.get(r["trace_id"]) == active["id"]]
    old = [r["rating"] for r in rows if versions.get(r["trace_id"]) == active["parent_id"]]
    worse, why = should_roll_back(new, old)
    if not worse:
        return None
    client.table("rag_configs").update({"status": "rejected", "reason": f"rolled back: {why}"}).eq("id", active["id"]).execute()
    client.table("rag_configs").update({"status": "active", "activated_at": _now().isoformat()}).eq("id", active["parent_id"]).execute()
    invalidate_cache()
    return why


def run_cycle(client, judge: Judge, *, tune: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {}
    active = _active(client)
    if active is None:
        return {"error": "no active configuration"}
    rolled = _roll_back_if_worse(client, active)
    if rolled:
        report["rolled_back"] = rolled
        active = _active(client)
    report["labels"] = label_new_feedback(client, judge)
    report["reasks"] = label_reasks(client, judge)
    if not tune or rolled:
        return report
    activated = active.get("activated_at")
    if active.get("parent_id") and activated and _now() - _parse(activated) < COOLDOWN:
        report["tuning"] = {"action": "cooldown", "reasons": ["active configuration is too recent to judge"]}
        return report
    current = from_dict(active["params"])
    proposal = propose([l for l, _ in _accepted_labels(client)], current)
    report["tuning"] = proposal
    if proposal["action"] == "promote":
        client.table("rag_configs").update({"status": "retired"}).eq("id", active["id"]).execute()
        created = client.table("rag_configs").insert({
            "params": proposal["params"], "status": "active", "parent_id": active["id"],
            "reason": "; ".join(proposal["reasons"]), "metrics": proposal["metrics"],
            "activated_at": _now().isoformat()}).execute().data
        invalidate_cache()
        report["adopted_version"] = created[0]["id"] if created else None
    return report
