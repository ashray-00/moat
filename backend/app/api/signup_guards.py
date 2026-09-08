"""Signup soft-gates: disposable email domains + global create rate (Postgres)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from app.config import settings
from app.db import engine

# Common throwaway providers — not exhaustive; extend via BLOCKED_EMAIL_DOMAINS.
_BUILTIN_DISPOSABLE = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.de",
        "10minutemail.com",
        "tempmail.com",
        "temp-mail.org",
        "yopmail.com",
        "trashmail.com",
        "discard.email",
        "getnada.com",
        "sharklasers.com",
        "spamgourmet.com",
        "maildrop.cc",
        "mailnesia.com",
    }
)


def _blocked_domains() -> set[str]:
    extra = {
        d.strip().lower()
        for d in (settings.blocked_email_domains or "").split(",")
        if d.strip()
    }
    if not settings.block_disposable_email:
        return extra
    return set(_BUILTIN_DISPOSABLE) | extra


def email_domain(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e:
        return ""
    return e.rsplit("@", 1)[-1]


def is_disposable_email(email: str) -> bool:
    domain = email_domain(email)
    return bool(domain) and domain in _blocked_domains()


def assert_email_allowed(email: str | None) -> None:
    if not email:
        return
    if is_disposable_email(email):
        raise HTTPException(
            400,
            "This email provider is not allowed. Use a permanent address.",
        )


async def assert_signup_rate_ok() -> None:
    """Limit new users/hour globally (demo abuse). 0 disables."""
    limit = int(settings.max_signups_per_hour or 0)
    if limit <= 0:
        return
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT count(*)::int AS n FROM users "
                    "WHERE created_at >= now() - interval '1 hour'"
                )
            )
        ).one()
    if int(row.n) >= limit:
        raise HTTPException(
            429,
            "Too many new accounts right now. Try again later.",
        )
