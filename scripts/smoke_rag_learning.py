"""Live smoke test of the self-improvement cycle (synthetic ratings, fake judge, restores everything).

    PYTHONPATH=. python scripts/smoke_rag_learning.py
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import create_client

from document_engine.rag_config import invalidate_cache, load_active
from document_engine.rag_learning import run_cycle

load_dotenv(".env")
client = create_client(os.environ["SUPABASE_URL"], os.environ.get("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_SERVICE_ROLE_KEY"])
TAG = "smoke-learning"
property_id = client.table("properties").select("id").limit(1).execute().data[0]["id"]
before = client.table("rag_configs").select("id").eq("status", "active").execute().data[0]["id"]
users = [str(uuid.uuid4()) for _ in range(5)]
start = datetime.now(timezone.utc) - timedelta(days=2)


def seed(user, rating, relevance, n):
    for i in range(n):
        when = (start + timedelta(minutes=10 * i + users.index(user))).isoformat()
        trace = client.table("agent_retrieval_traces").insert({
            "property_id": property_id, "user_id": user, "question": f"{TAG} {user[:4]} {rating} {i}",
            "strength": "weak", "best_relevance": relevance, "best_similarity": 0.5, "chunk_ids": [],
            "candidates": [{"chunk_id": "x", "similarity": 0.5, "relevance": relevance}],
            "config_version": before, "created_at": when}).execute().data[0]
        client.table("agent_answer_feedback").insert({
            "property_id": property_id, "user_id": user, "question": trace["question"], "answer": "risposta",
            "rating": rating, "trace_id": trace["id"], "created_at": when}).execute()


try:
    for u in users:
        seed(u, 1, 0.95, 12)
        seed(u, -1, 0.68, 12)
    judge = lambda question, answer, passages: (" 1 " in f" {question[-5:]} ") or question.split()[-2] == "1"
    report = run_cycle(client, judge)
    print("labels:", report["labels"])
    print("tuning:", report["tuning"]["action"], report["tuning"]["reasons"])
    invalidate_cache()
    version, params = load_active(client)
    print("active version:", version, "weak_relevance:", params.weak_relevance)
    assert report["labels"]["accepted"] >= 100 and report["labels"]["accepted"] + report["labels"]["review"] == 120
    assert report["tuning"]["action"] == "promote" and version != before
    assert 0.65 < params.weak_relevance <= 0.70
    history = client.table("rag_configs").select("id,status,parent_id,reason").order("id").execute().data
    print([(h["id"], h["status"], h["parent_id"]) for h in history[-2:]])
    print("OK")
finally:
    client.table("agent_answer_feedback").delete().like("question", f"{TAG}%").execute()
    client.table("agent_retrieval_traces").delete().like("question", f"{TAG}%").execute()
    client.table("rag_configs").update({"status": "retired"}).eq("status", "active").neq("id", before).execute()
    client.table("rag_configs").delete().gt("id", before).execute()
    client.table("rag_configs").update({"status": "active"}).eq("id", before).execute()
    invalidate_cache()
