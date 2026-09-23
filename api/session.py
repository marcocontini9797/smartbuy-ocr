"""User-scoped Supabase access: never use service-role for workspace reads."""
import os
from fastapi import Header, HTTPException
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def user_client(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to access your properties")
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise HTTPException(503, "Authentication is not configured")
    client = create_client(url, key)
    token = authorization[7:]
    try:
        result = client.auth.get_user(token)
        if not result.user:
            raise ValueError("No user")
    except Exception:
        raise HTTPException(401, "Session invalid or expired")
    client.postgrest.auth(token)
    client.smartbuy_user_id = str(result.user.id)
    return client
