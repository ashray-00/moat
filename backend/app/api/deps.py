from functools import lru_cache

from fastapi import Header, HTTPException
import jwt
from jwt import PyJWKClient

from app.config import settings


@lru_cache
def _jwks_client() -> PyJWKClient:
    base = settings.supabase_url.rstrip("/")
    return PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json")


async def current_user(authorization: str = Header(...)) -> str:
    if not settings.supabase_url:
        raise HTTPException(500, "SUPABASE_URL is not configured")
    try:
        token = authorization.removeprefix("Bearer ").strip()
        key = _jwks_client().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
        )
        return payload["sub"]
    except Exception:
        raise HTTPException(401, "invalid token")
