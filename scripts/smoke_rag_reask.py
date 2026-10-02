"""Live smoke test of implicit re-ask labelling (fake judge, cleans up).

    PYTHONPATH=. python scripts/smoke_rag_reask.py
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import create_client

from document_engine.rag_learning import label_reasks

load_dotenv(".env")
client = create_client(os.environ["SUPABASE_URL"], os.environ.get("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_SERVICE_ROLE_KEY"])
property_id = client.table("properties").select("id").limit(1).execute().data[0]["id"]
user = str(uuid.uuid4())
now = datetime.now(timezone.utc)
vector = [0.1] * 1536
ids = []
try:
    for i, seconds in enumerate((0, 40)):
        ids.append(client.table("agent_retrieval_traces").insert({
            "property_id": property_id, "user_id": user, "question": f"smoke-reask {i}", "strength": "weak",
            "chunk_ids": [], "question_embedding": vector, "answer": "non so",
            "created_at": (now - timedelta(minutes=5) + timedelta(seconds=seconds)).isoformat()}).execute().data[0]["id"])
    counts = label_reasks(client, lambda q, a, p: False)
    print(counts)
    labels = client.table("rag_feedback_labels").select("trace_id,source,rating,weight,verdict").in_("trace_id", ids).execute().data
    print(labels)
    assert counts["accepted"] == 1 and len(labels) == 1 and labels[0]["trace_id"] == ids[0] and labels[0]["rating"] == -1
    print("OK")
finally:
    client.table("agent_retrieval_traces").delete().like("question", "smoke-reask%").execute()
