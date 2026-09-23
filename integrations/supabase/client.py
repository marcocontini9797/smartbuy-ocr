"""
SmartBuy Supabase Client
"""

import os

from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
)


if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL o SUPABASE_KEY mancanti nel file .env"
    )


supabase: Client = create_client(
    SUPABASE_URL.strip(),
    SUPABASE_KEY.strip()
)
