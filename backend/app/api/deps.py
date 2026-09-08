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
    from app.api.signup_guards import assert_email_allowed, assert_signup_rate_ok

    async with engine.begin() as conn:
        existing = (
            await conn.execute(
                text("SELECT user_id FROM users WHERE user_id=:u"),
                {"u": user_id},
            )
        ).first()
        if existing:
            if email:
                await conn.execute(
                    text(
                        "UPDATE users SET email=COALESCE(:e, email), "
                        "updated_at=now() WHERE user_id=:u"
                    ),
                    {"u": user_id, "e": email},
                )
            return user_id

    # New account only — soft abuse gates (not applied on every request).
    assert_email_allowed(email)
    await assert_signup_rate_ok()
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


async def get_raw_user_plan(user_id: str) -> str:
    """Plan stored on the users row (ignores org inheritance)."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT plan FROM users WHERE user_id=:u"), {"u": user_id}
            )
        ).first()
    return row.plan if row else "free"


async def get_user_plan(user_id: str) -> str:
    """Effective plan: Team org members inherit the owner's Team entitlements."""
    from app.api.limits import normalize_plan
    from app.orgs.store import get_org_for_user

    own = normalize_plan(await get_raw_user_plan(user_id))
    org = await get_org_for_user(user_id)
    if not org:
        return own
    owner_id = org.get("owner_user_id")
    if not owner_id or owner_id == user_id:
        return own
    owner_plan = normalize_plan(await get_raw_user_plan(owner_id))
    if owner_plan == "team":
        return "team"
    return own


async def current_user(authorization: str = Header(...)) -> str:
    payload = _decode_bearer(authorization)
    user_id = payload["sub"]
    await get_or_create_user(user_id, payload.get("email"))
    return user_id


async def current_user_email(
    authorization: str = Header(...),
) -> tuple[str, str]:
    """Return (user_id, email). Email is required for invite accept binding."""
    payload = _decode_bearer(authorization)
    user_id = payload["sub"]
    email = (payload.get("email") or "").strip()
    if not email:
        raise HTTPException(400, "JWT is missing email claim required for this action.")
    await get_or_create_user(user_id, email)
    return user_id, email.lower()


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
RequiredUserEmail = Annotated[tuple[str, str], Depends(current_user_email)]
