"""How much a human rating is worth. Ratings are evidence, never truth.

A rating becomes a *label* the learning loop may use only after it survives three checks:

1. an independent judge (a language model reading the actual passages) must not contradict it;
2. the person rating must have a track record: reliability is the share of their past ratings the
   judge agreed with (with a prior, so a new user starts neutral and cannot swing anything);
3. the rating must not look like noise: bursts, rubber-stamping, or contradicting themselves.

Disagreement between human and judge is not resolved by picking a side: the case is parked for
review and excluded from learning. This makes the loop conservative on purpose — a wrongly
discarded rating costs a little data, a wrongly accepted one can move production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

PRIOR_AGREE = 3.0           # Beta prior: a new user is worth 3 agreements out of 6, i.e. 0.5
PRIOR_TOTAL = 6.0
MUTE_BELOW = 0.35           # a user the judge mostly contradicts stops counting
ACCEPT_AT = 0.45            # label weight needed to be used for learning
BURST_LIMIT = 20            # ratings in an hour
RUBBER_STAMP_RUN = 10       # identical consecutive ratings


@dataclass
class UserHistory:
    agreed: int = 0                       # past explicit labels the judge agreed with
    judged: int = 0                       # past explicit labels the judge ruled on
    recent_hour: int = 0                  # ratings in the last hour (this one excluded)
    recent_ratings: Sequence[int] = ()    # latest ratings, newest last
    contradicts_self: bool = False        # rated the same question both ways


@dataclass
class Decision:
    weight: float
    verdict: str                          # accepted | review | rejected
    reasons: list[str] = field(default_factory=list)


def reliability(history: UserHistory) -> float:
    return (history.agreed + PRIOR_AGREE) / (history.judged + PRIOR_TOTAL)


def decide_explicit(rating: int, judge_supported: bool | None, history: UserHistory) -> Decision:
    """`judge_supported`: True/False when the judge could read the passages, None when it could not."""
    reasons: list[str] = []
    weight = reliability(history)
    if weight < MUTE_BELOW:
        return Decision(0.0, "rejected", [f"user_reliability={weight:.2f}"])
    if history.contradicts_self:
        return Decision(0.0, "rejected", ["contradicts_self"])
    if history.recent_hour >= BURST_LIMIT:
        weight *= 0.2
        reasons.append("burst")
    run = list(history.recent_ratings)[-RUBBER_STAMP_RUN:]
    if len(run) == RUBBER_STAMP_RUN and len(set(run)) == 1 and run[-1] == rating:
        weight *= 0.5
        reasons.append("rubber_stamping")

    if judge_supported is None:
        # nobody checked it: only a user with a clear record, and never for learning on 👎
        verdict = "accepted" if weight >= 0.7 and rating == 1 else "review"
        return Decision(weight if verdict == "accepted" else 0.0, verdict, reasons + ["no_judge"])

    human_says_good = rating == 1
    if human_says_good == judge_supported:
        reasons.append("judge_agrees")
        return Decision(weight, "accepted" if weight >= ACCEPT_AT else "review", reasons)
    reasons.append("judge_disagrees")
    return Decision(0.0, "review", reasons)


IMPLICIT_WEIGHT = 0.3


def decide_implicit(judge_supported: bool | None) -> Decision:
    """The user asked the same thing again within minutes: weak evidence the first answer fell short.
    It counts only if the judge also finds that answer unsupported by its passages, and only as a
    low-weight negative; without the judge's confirmation it is parked."""
    if judge_supported is False:
        return Decision(IMPLICIT_WEIGHT, "accepted", ["reask", "judge_agrees"])
    return Decision(0.0, "review", ["reask", "judge_disagrees" if judge_supported else "no_judge"])
