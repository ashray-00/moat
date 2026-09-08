from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException
import jwt
from jwt import PyJWKClient
from sqlalchemy import text

from app.config import settings
from app.db import engine


@lru_cache
def _jwks_client() -> PyJWKClient:
    base = settings.supabase_url.rstrip("/")
    return PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json")


def _decode_bearer(authorization: str) -> dict:
    if not settings.supabase_url:
        raise HTTPException(500, "SUPABASE_URL is not configured")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "invalid token")
    try:
        key = _jwks_client().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "invalid token")


async def get_or_create_user(user_id: str, email: str | None = None) -> str:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (user_id, email) VALUES (:u, :e) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "email = COALESCE(EXCLUDED.email, users.email), "
                "updated_at = now()"
            ),
            {"u": user_id, "e": email},
        )
    return user_id


async def get_user_plan(user_id: str) -> str:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT plan FROM users WHERE user_id=:u"), {"u": user_id}
            )
        ).first()
    return row.plan if row else "free"


async def current_user(authorization: str = Header(...)) -> str:
    payload = _decode_bearer(authorization)
    user_id = payload["sub"]
    await get_or_create_user(user_id, payload.get("email"))
    return user_id


async def optional_user(
    authorization: str | None = Header(default=None),
) -> str | None:
    if not authorization:
        if settings.auth_required:
            raise HTTPException(401, "authorization required")
        return None
    payload = _decode_bearer(authorization)
    user_id = payload["sub"]
    await get_or_create_user(user_id, payload.get("email"))
    return user_id


async def require_user(
    authorization: str = Header(...),
) -> str:
    return await current_user(authorization)


OptionalUser = Annotated[str | None, Depends(optional_user)]
RequiredUser = Annotated[str, Depends(require_user)]
