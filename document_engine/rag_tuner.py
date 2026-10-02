"""Propose, test and (only if clearly better) adopt new relevance-gate parameters from accepted labels.

The gate is replayed exactly from what a trace stored (candidate similarity and relevance, whether an
identifier matched), so a candidate setting is judged on real past questions without calling any model.

A label is a trace plus what we now believe about it (see rag_trust):
- "good":  an answer people found useful and the judge found supported — it should have been shown;
- "bad":   an answer people rejected and the judge found unsupported — retrieval had nothing to
           support it, so the right behaviour was to say so ("none").
A 👎 the judge finds supported is not a retrieval problem (tone, outdated document...) and is not used here.

Guards (all must hold, otherwise nothing changes): enough labels from enough different people, no
single user above MAX_USER_SHARE of the weight, both classes represented, the change within the
per-cycle step limit and the hard bounds, the useful answers still kept, and an improvement whose
bootstrap lower bound is above zero — i.e. unlikely to be luck.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Sequence

from document_engine.rag_config import BOUNDS, MAX_STEP, RagParams, clamp, step_limited, to_dict

MIN_LABELS = 40
MIN_PER_CLASS = 10
MIN_USERS = 3
MAX_USER_SHARE = 0.20
KEEP_GOOD = 0.95
MIN_GAIN = 0.01
BOOTSTRAPS = 400


@dataclass
class Label:
    kind: str                       # "good" | "bad"
    weight: float
    user_id: str | None
    strength: str
    identifier_hit: bool
    candidates: Sequence[dict[str, Any]]
    best_similarity: float


def simulate(label: Label, params: RagParams) -> str:
    """The strength retrieval would have declared under `params` (same rules as rag_search.judge)."""
    if label.identifier_hit:
        return "strong"
    head = list(label.candidates)[:3]
    if not head:
        return "none"
    relevances = [c.get("relevance") for c in head]
    if any(r is not None for r in relevances):
        best = max(float(r or 0.0) for r in relevances)
        floor, strong = params.weak_relevance, params.strong_relevance
    else:
        best = max(float(c.get("similarity") or 0.0) for c in head)
        floor, strong = params.weak_similarity, params.strong_similarity
    return "strong" if best >= strong else "weak" if best >= floor else "none"


def _capped(labels: Sequence[Label]) -> list[float]:
    """Weights with no user above MAX_USER_SHARE of the resulting total (a few people cannot steer the
    system): a user's weight is limited to share/(1-share) of everyone else's."""
    per_user: dict[str | None, float] = {}
    for l in labels:
        per_user[l.user_id] = per_user.get(l.user_id, 0.0) + l.weight
    total = sum(per_user.values())
    ratio = MAX_USER_SHARE / (1 - MAX_USER_SHARE)
    scale = {u: min(1.0, ratio * (total - w) / w) if w else 1.0 for u, w in per_user.items()}
    return [l.weight * scale[l.user_id] for l in labels]


def score(labels: Sequence[Label], weights: Sequence[float], params: RagParams) -> dict[str, float]:
    """Balanced accuracy of the gate: share of good answers kept and of bad ones refused, each side
    weighted equally so a flood of 👍 cannot make a gate that never refuses look good."""
    kept = refused = good_w = bad_w = 0.0
    for label, weight in zip(labels, weights):
        shown = simulate(label, params) != "none"
        if label.kind == "good":
            good_w += weight
            kept += weight if shown else 0.0
        else:
            bad_w += weight
            refused += weight if not shown else 0.0
    keep_rate = kept / good_w if good_w else 1.0
    refuse_rate = refused / bad_w if bad_w else 1.0
    return {"keep_good": keep_rate, "refuse_bad": refuse_rate, "balanced": (keep_rate + refuse_rate) / 2}


def _bootstrap_gain(labels: Sequence[Label], weights: Sequence[float], old: RagParams, new: RagParams) -> float:
    """5th percentile of (new - old) balanced accuracy over resamples: positive = a real improvement."""
    rng = random.Random(7)
    gains = []
    n = len(labels)
    for _ in range(BOOTSTRAPS):
        picks = [rng.randrange(n) for _ in range(n)]
        sample = [labels[i] for i in picks]
        w = [weights[i] for i in picks]
        gains.append(score(sample, w, new)["balanced"] - score(sample, w, old)["balanced"])
    gains.sort()
    return gains[int(0.05 * len(gains))]


def _candidates(current: RagParams) -> list[RagParams]:
    out = []
    for dr in (-1, -0.5, 0, 0.5, 1):
        for ds in (-1, -0.5, 0, 0.5, 1):
            wanted = RagParams(
                weak_relevance=current.weak_relevance + dr * MAX_STEP["weak_relevance"],
                strong_relevance=current.strong_relevance,
                weak_similarity=current.weak_similarity + ds * MAX_STEP["weak_similarity"],
                strong_similarity=current.strong_similarity)
            out.append(step_limited(current, clamp(wanted)))
    return list({to_dict(p).__repr__(): p for p in out}.values())


def propose(labels: Sequence[Label], current: RagParams) -> dict[str, Any]:
    """{"action": "promote"|"keep"|"insufficient", "params": ..., "metrics": ..., "reasons": [...]}"""
    good = [l for l in labels if l.kind == "good"]
    bad = [l for l in labels if l.kind == "bad"]
    users = {l.user_id for l in labels if l.user_id}
    problems = []
    if len(labels) < MIN_LABELS:
        problems.append(f"labels {len(labels)}/{MIN_LABELS}")
    if min(len(good), len(bad)) < MIN_PER_CLASS:
        problems.append(f"good {len(good)} bad {len(bad)} (need {MIN_PER_CLASS} each)")
    if len(users) < MIN_USERS:
        problems.append(f"users {len(users)}/{MIN_USERS}")
    if problems:
        return {"action": "insufficient", "params": to_dict(current), "metrics": {"labels": len(labels)}, "reasons": problems}

    weights = _capped(labels)
    base = score(labels, weights, current)
    best, best_score = current, base
    for candidate in _candidates(current):
        result = score(labels, weights, candidate)
        if result["keep_good"] < KEEP_GOOD:
            continue
        if (result["balanced"], -sum(abs(getattr(candidate, k) - getattr(current, k)) for k in BOUNDS)) > \
           (best_score["balanced"], -sum(abs(getattr(best, k) - getattr(current, k)) for k in BOUNDS)):
            best, best_score = candidate, result
    metrics = {"labels": len(labels), "users": len(users), "before": base, "after": best_score}
    if best == current or best_score["balanced"] - base["balanced"] < MIN_GAIN:
        return {"action": "keep", "params": to_dict(current), "metrics": metrics, "reasons": ["no clear gain"]}
    # robustness: the gain must survive removing any single person's labels
    for user in users:
        rest = [(l, w) for l, w in zip(labels, weights) if l.user_id != user]
        r_labels, r_weights = [l for l, _ in rest], [w for _, w in rest]
        if score(r_labels, r_weights, best)["balanced"] - score(r_labels, r_weights, current)["balanced"] < MIN_GAIN:
            return {"action": "keep", "params": to_dict(current), "metrics": metrics,
                    "reasons": ["gain depends on a single user's ratings"]}
    lower = _bootstrap_gain(labels, weights, current, best)
    metrics["gain_lower_bound"] = round(lower, 4)
    if lower <= 0:
        return {"action": "keep", "params": to_dict(current), "metrics": metrics,
                "reasons": ["gain not significant (could be chance)"]}
    return {"action": "promote", "params": to_dict(best), "metrics": metrics,
            "reasons": [f"balanced accuracy {base['balanced']:.2f} -> {best_score['balanced']:.2f}, lower bound {lower:+.3f}"]}


ROLLBACK_MARGIN = 0.10
ROLLBACK_MIN = 20


def should_roll_back(new_ratings: Sequence[int], old_ratings: Sequence[int]) -> tuple[bool, str]:
    """Compare the share of accepted 👍 under the new configuration with the one it replaced."""
    if len(new_ratings) < ROLLBACK_MIN or len(old_ratings) < ROLLBACK_MIN:
        return False, "not enough ratings yet"
    new_rate = sum(1 for r in new_ratings if r == 1) / len(new_ratings)
    old_rate = sum(1 for r in old_ratings if r == 1) / len(old_ratings)
    if new_rate < old_rate - ROLLBACK_MARGIN:
        return True, f"approval fell from {old_rate:.2f} to {new_rate:.2f}"
    return False, f"approval {old_rate:.2f} -> {new_rate:.2f}"
