"""Learn the retrieval thresholds from real ratings.

Every answer an agent rates leaves a trace (how relevant retrieval judged its best passage, how
strong it called the evidence) and a 👍/👎. This looks at the two groups and says where the
relevance floor should sit: low enough to keep (almost) every answer agents found useful, high
enough to refuse the ones they did not. It only suggests: a threshold moves production for
every agent, so a person decides, and only once there is enough data to trust it.
"""

from __future__ import annotations

from typing import Any, Sequence

from document_engine.rag_search import STRONG_RELEVANCE, WEAK_RELEVANCE

MIN_PER_GROUP = 15          # fewer ratings than this per group and the picture is noise
KEEP_USEFUL = 0.95          # the floor must keep at least this share of the useful answers


def _percentile(values: Sequence[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(share * len(ordered))))]


def calibration_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """`rows`: one per rated trace, with `rating` (1/-1), `strength` and `best_relevance`."""
    reranked = [r for r in rows if r.get("best_relevance") is not None]
    useful = [float(r["best_relevance"]) for r in reranked if r["rating"] == 1]
    bad = [float(r["best_relevance"]) for r in reranked if r["rating"] == -1]
    report: dict[str, Any] = {
        "rated": len(rows), "useful": sum(1 for r in rows if r["rating"] == 1),
        "not_useful": sum(1 for r in rows if r["rating"] == -1),
        "current": {"weak": WEAK_RELEVANCE, "strong": STRONG_RELEVANCE},
        "bad_despite_strong": sum(1 for r in rows if r["rating"] == -1 and r.get("strength") == "strong"),
        "useful_despite_weak": sum(1 for r in rows if r["rating"] == 1 and r.get("strength") == "weak"),
    }
    if len(useful) < MIN_PER_GROUP or len(bad) < MIN_PER_GROUP:
        report["suggestion"] = None
        report["note"] = (f"Dati insufficienti: servono almeno {MIN_PER_GROUP} risposte utili e {MIN_PER_GROUP} "
                          f"non utili con rilevanza misurata (ora {len(useful)} e {len(bad)}).")
        return report
    # the floor that still keeps KEEP_USEFUL of the useful answers
    floor = _percentile(useful, 1 - KEEP_USEFUL)
    refused = sum(1 for v in bad if v < floor) / len(bad)
    report["suggestion"] = {"weak": round(floor, 2), "bad_answers_refused": round(refused, 2),
                            "useful_answers_kept": KEEP_USEFUL}
    report["note"] = ("Soglia debole suggerita " + f"{floor:.2f} (ora {WEAK_RELEVANCE}): terrebbe il "
                      f"{int(KEEP_USEFUL * 100)}% delle risposte utili e rifiuterebbe il {int(refused * 100)}% di quelle "
                      "segnalate. Da applicare a mano in rag_search.py dopo averla confrontata con evaluation/.")
    return report
