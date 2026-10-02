"""Live smoke test of the feedback loop against the real database (fake embeddings, cleans up after itself).

    PYTHONPATH=. python scripts/smoke_rag_feedback.py
"""

import os

import numpy as np
from dotenv import load_dotenv
from supabase import create_client

from document_engine.rag_index import index_document
from document_engine.rag_search import retrieve
from document_engine.rag_service import record_trace
from document_engine.rag_store import SupabaseChunkStore

load_dotenv(".env")
client = create_client(os.environ["SUPABASE_URL"], os.environ.get("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_SERVICE_ROLE_KEY"])

prop = client.table("properties").select("*").limit(1).execute().data[0]
owner = next(prop[k] for k in ("user_id", "owner_id", "agent_id") if k in prop)
property_id = prop["id"]
document_id = 15      # an existing document: service_role cannot delete rows of documents, so none is created


def embed(texts):
    """Bag-of-words vectors: texts sharing words are close, like a real embedding, with no API call."""
    out = []
    for t in texts:
        v = np.zeros(1536)
        for word in t.lower().replace(".", " ").replace(",", " ").split():
            v[sum(ord(c) * 31 ** i for i, c in enumerate(word)) % 1536] += 1.0
        out.append(v / (np.linalg.norm(v) or 1.0))
    return np.array(out)


try:
    text = "--- PAGINA 1 ---\nArt. 1 Ipoteca\nSull'immobile grava ipoteca volontaria di euro 150.000 a favore della Banca Test.\n\nArt. 2 Spese\nLe spese condominiali arretrate sono a carico del venditore."
    n = index_document(client, property_id=property_id, document_id=document_id, document_type="atto_compravendita",
                       file_name="smoke_rag.pdf", full_text=text, embed=embed, embedding_model="fake")
    print("chunks indexed:", n)
    store = SupabaseChunkStore(client)
    result = retrieve(store, embed, property_id, "ipoteca banca test")
    print("retrieved:", [p.chunk_id[:8] for p in result.ranked], result.strength)
    assert result.ranked and result.vector

    row = {"property_id": property_id, "user_id": owner, "question": "ipoteca banca test", "strength": result.strength,
           "best_relevance": None, "best_similarity": result.best_similarity,
           "chunk_ids": [p.chunk_id for p in result.ranked], "question_embedding": result.vector}
    trace = client.table("agent_retrieval_traces").insert(row).execute().data[0]
    print("trace stored:", trace["id"][:8])
    client.table("agent_answer_feedback").insert({
        "property_id": property_id, "user_id": owner, "question": "ipoteca banca test", "answer": "x", "rating": 1,
        "trace_id": trace["id"]}).execute()

    hints = store.feedback_hints(property_id, result.vector, 0.88)
    print("hints:", len(hints), "net:", set(hints.values()))
    assert hints and all(v == 1.0 for v in hints.values())
    again = retrieve(store, embed, property_id, "ipoteca banca test")
    print("hints applied on repeat:", again.hints_applied)
    assert again.hints_applied >= 1
    far = store.feedback_hints(property_id, embed(["tutt'altro"])[0].tolist(), 0.88)
    assert far == {}, "a dissimilar question must not inherit the feedback"
    print("OK")
finally:
    client.table("agent_answer_feedback").delete().eq("question", "ipoteca banca test").execute()
    client.table("agent_retrieval_traces").delete().eq("question", "ipoteca banca test").execute()
    client.table("document_chunks").delete().eq("document_id", document_id).execute()
