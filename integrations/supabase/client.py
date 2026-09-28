"""
SmartBuy privileged Supabase client.

Use only in backend-only flows that intentionally bypass user RLS
(e.g. seller-lead persistence and mechanical signing after authorization).
"""

import os

from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
)


if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL e una chiave admin Supabase mancanti nel file .env"
    )


supabase: Client = create_client(
    SUPABASE_URL.strip(),
    SUPABASE_KEY.strip()
)
