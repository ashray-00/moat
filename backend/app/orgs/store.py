"""Team org membership and invites."""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import text

from app.db import engine


async def get_org_for_user(user_id: str) -> dict | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT o.org_id, o.name, o.owner_user_id, m.role "
                    "FROM org_members m JOIN orgs o ON o.org_id=m.org_id "
                    "WHERE m.user_id=:u"
                ),
                {"u": user_id},
            )
        ).mappings().first()
    return dict(row) if row else None


async def ensure_team_org(owner_user_id: str, name: str | None = None) -> dict:
    existing = await get_org_for_user(owner_user_id)
    if existing:
        return existing
    org_id = str(uuid.uuid4())
    label = name or "Team"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO orgs (org_id, name, owner_user_id) VALUES (:o, :n, :u)"
            ),
            {"o": org_id, "n": label, "u": owner_user_id},
        )
        await conn.execute(
            text(
                "INSERT INTO org_members (org_id, user_id, role) "
                "VALUES (:o, :u, 'owner')"
            ),
            {"o": org_id, "u": owner_user_id},
        )
    return {
        "org_id": org_id,
        "name": label,
        "owner_user_id": owner_user_id,
        "role": "owner",
    }


async def list_members(org_id: str) -> list[dict]:
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT user_id, role, created_at FROM org_members "
                    "WHERE org_id=:o ORDER BY created_at"
                ),
                {"o": org_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def member_count(org_id: str) -> int:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT count(*) AS n FROM org_members WHERE org_id=:o"),
                {"o": org_id},
            )
        ).one()
    return int(row.n)


async def create_invite(
    org_id: str, email: str, invited_by: str
) -> dict:
    invite_id = secrets.token_urlsafe(16)
    em = email.strip().lower()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO org_invites (invite_id, org_id, email, invited_by, status) "
                "VALUES (:i, :o, :e, :b, 'pending')"
            ),
            {"i": invite_id, "o": org_id, "e": em, "b": invited_by},
        )
    return {"invite_id": invite_id, "org_id": org_id, "email": em, "status": "pending"}


async def get_pending_invite(invite_id: str) -> dict | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT invite_id, org_id, email, invited_by, status "
                    "FROM org_invites WHERE invite_id=:i AND status='pending'"
                ),
                {"i": invite_id},
            )
        ).mappings().first()
    return dict(row) if row else None


async def accept_invite(invite_id: str, user_id: str, user_email: str | None) -> dict:
    inv = await get_pending_invite(invite_id)
    if not inv:
        raise ValueError("invite_not_found")
    if user_email and inv["email"] and user_email.strip().lower() != inv["email"]:
        raise ValueError("email_mismatch")
    if await get_org_for_user(user_id):
        raise ValueError("already_in_org")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO org_members (org_id, user_id, role) "
                "VALUES (:o, :u, 'member')"
            ),
            {"o": inv["org_id"], "u": user_id},
        )
        await conn.execute(
            text(
                "UPDATE org_invites SET status='accepted' WHERE invite_id=:i"
            ),
            {"i": invite_id},
        )
    return await get_org_for_user(user_id) or {}
