"""User-scoped Supabase access: never use an admin key for workspace reads."""
import hashlib
import os
import time

from fastapi import Header, HTTPException
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def _public_key() -> str | None:
    return os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")


# A verified token is remembered for a short time: every request used to pay a network round trip to
# Supabase Auth just to learn who the caller is. The window is short on purpose, so a revoked or expired
# session stops working within TOKEN_CACHE_SECONDS.
TOKEN_CACHE_SECONDS = 60
_VERIFIED: dict[str, tuple[float, str]] = {}


def _verified_user(client, token: str) -> str:
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    hit = _VERIFIED.get(key)
    if hit and hit[0] > now:
        return hit[1]
    result = client.auth.get_user(token)
    if not result.user:
        raise ValueError("No user")
    if len(_VERIFIED) > 2000:
        for stale in [k for k, (until, _) in _VERIFIED.items() if until <= now]:
            _VERIFIED.pop(stale, None)
    _VERIFIED[key] = (now + TOKEN_CACHE_SECONDS, str(result.user.id))
    return str(result.user.id)


def user_client(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to access your properties")

    url, key = os.getenv("SUPABASE_URL"), _public_key()
    if not url or not key:
        raise HTTPException(503, "Authentication is not configured")

    client = create_client(url, key)
    token = authorization[7:]
    try:
        user_id = _verified_user(client, token)
    except Exception:
        raise HTTPException(401, "Session invalid or expired")

    client.postgrest.auth(token)
    # Storage is built lazily from these headers: it must act as the user too.
    client.options.headers["Authorization"] = f"Bearer {token}"
    client.smartbuy_user_id = user_id
    return client
