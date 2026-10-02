"""Index the documents already uploaded (run once, safe to repeat).

    PYTHONPATH=. python scripts/backfill_rag_index.py [limit]
"""

import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from document_engine.rag_service import backfill_missing

load_dotenv(".env")

client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
print(backfill_missing(client, limit=int(sys.argv[1]) if len(sys.argv) > 1 else 200))
