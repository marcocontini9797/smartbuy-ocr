from document_engine.rag_config import BOUNDS, RagParams, clamp, from_dict, step_limited
from document_engine.rag_learning import build_history
from document_engine.rag_trust import UserHistory, decide_explicit, reliability
from document_engine.rag_tuner import Label, propose, should_roll_back, simulate


# --- trust -------------------------------------------------------------------------------------------

def test_new_user_is_neutral_and_judge_agreement_accepts():
    assert reliability(UserHistory()) == 0.5
    d = decide_explicit(1, True, UserHistory())
    assert d.verdict == "accepted" and d.weight == 0.5


def test_disagreement_with_judge_is_parked_not_used():
    assert decide_explicit(1, False, UserHistory()).verdict == "review"
    assert decide_explicit(-1, True, UserHistory()).weight == 0.0


def test_unreliable_user_is_muted():
    d = decide_explicit(-1, False, UserHistory(agreed=0, judged=20))
    assert d.verdict == "rejected" and d.weight == 0.0


def test_burst_rubber_stamp_and_self_contradiction_are_discounted():
    normal = decide_explicit(1, True, UserHistory(agreed=20, judged=20)).weight
    burst = decide_explicit(1, True, UserHistory(agreed=20, judged=20, recent_hour=25)).weight
    stamp = decide_explicit(1, True, UserHistory(agreed=20, judged=20, recent_ratings=[1] * 10)).weight
    assert burst < normal * 0.3 and stamp < normal
    assert decide_explicit(1, True, UserHistory(contradicts_self=True)).verdict == "rejected"


def test_without_judge_only_trusted_positive_is_accepted():
    assert decide_explicit(1, None, UserHistory(agreed=30, judged=30)).verdict == "accepted"
    assert decide_explicit(-1, None, UserHistory(agreed=30, judged=30)).verdict == "review"
    assert decide_explicit(1, None, UserHistory()).verdict == "review"


def test_build_history_counts_agreement_burst_and_contradiction():
    fb = {"id": "9", "question": "Ipoteca?", "rating": 1, "created_at": "2026-10-02T10:00:00+00:00"}
    others = [{"id": str(i), "question": f"q{i}", "rating": 1, "created_at": f"2026-10-02T09:{30 + i}:00+00:00"} for i in range(5)]
    others.append({"id": "x", "question": "ipoteca?", "rating": -1, "created_at": "2026-10-01T10:00:00+00:00"})
    past = [{"rating": 1, "judge_supported": True}, {"rating": 1, "judge_supported": False}, {"rating": -1, "judge_supported": None}]
    h = build_history(fb, others, past)
    assert (h.agreed, h.judged, h.recent_hour, h.contradicts_self) == (1, 2, 5, True)


# --- config bounds --------------------------------------------------------------------------------------

def test_params_never_leave_bounds_or_move_too_far():
    wild = clamp(RagParams(weak_relevance=0.99, strong_relevance=0.1, weak_similarity=0.0, strong_similarity=0.9))
    for key, (lo, hi) in BOUNDS.items():
        assert lo <= getattr(wild, key) <= hi
    assert wild.strong_relevance >= wild.weak_relevance + 0.05
    stepped = step_limited(RagParams(), RagParams(weak_relevance=0.5))
    assert abs(stepped.weak_relevance - 0.65) <= 0.05 + 1e-9
    assert from_dict({"weak_relevance": 5, "junk": 1}).weak_relevance == BOUNDS["weak_relevance"][1]


# --- tuner -----------------------------------------------------------------------------------------------

def label(kind, relevance, user, weight=1.0):
    return Label(kind=kind, weight=weight, user_id=user, strength="weak", identifier_hit=False,
                 candidates=[{"similarity": 0.5, "relevance": relevance}], best_similarity=0.5)


def test_simulate_follows_the_gate():
    p = RagParams()
    assert simulate(label("good", 0.9, "u"), p) == "strong"
    assert simulate(label("good", 0.7, "u"), p) == "weak"
    assert simulate(label("good", 0.4, "u"), p) == "none"
    assert simulate(Label("good", 1, "u", "none", True, [], 0.0), p) == "strong"


def dataset(n_users=5, bad_rel=0.68, per=12):
    out = []
    for u in range(n_users):
        out += [label("good", 0.95, f"u{u}") for _ in range(per)]
        out += [label("bad", bad_rel, f"u{u}") for _ in range(per)]
    return out


def test_tuner_waits_for_enough_data_and_people():
    assert propose(dataset(per=2), RagParams())["action"] == "insufficient"
    assert propose(dataset(n_users=2), RagParams())["action"] == "insufficient"


def test_tuner_raises_the_floor_when_bad_answers_sit_just_above_it():
    result = propose(dataset(bad_rel=0.68), RagParams())
    assert result["action"] == "promote"
    assert result["params"]["weak_relevance"] > 0.65
    assert result["params"]["weak_relevance"] <= 0.70      # one bounded step
    assert result["metrics"]["after"]["keep_good"] >= 0.95


def test_tuner_does_not_change_without_a_clear_gain():
    assert propose(dataset(bad_rel=0.2), RagParams())["action"] == "keep"


def test_one_user_cannot_steer_the_gate():
    labels = dataset(n_users=5, bad_rel=0.2)
    labels += [label("bad", 0.68, "troll", weight=1.0) for _ in range(60)]    # a flood from one account
    assert propose(labels, RagParams())["action"] == "keep"


def test_tuner_never_sacrifices_useful_answers():
    labels = dataset(bad_rel=0.9)          # bad answers are as relevant as good ones: no floor separates them
    result = propose(labels, RagParams())
    assert result["action"] == "keep"


def test_rollback_only_with_enough_evidence_of_decline():
    assert should_roll_back([1] * 10, [1] * 30)[0] is False
    assert should_roll_back([1] * 10 + [-1] * 15, [1] * 25 + [-1] * 5)[0] is True
    assert should_roll_back([1] * 24 + [-1], [1] * 25 + [-1] * 5)[0] is False
