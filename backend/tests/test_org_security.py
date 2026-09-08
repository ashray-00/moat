import pytest
from fastapi import HTTPException

from app.api import org as org_api
from app.orgs import store as orgs


@pytest.mark.asyncio
async def test_accept_requires_email_match(monkeypatch):
    async def fake_accept(invite_id, user_id, user_email, *, seat_limit):
        if user_email != "invitee@x.com":
            raise ValueError("email_mismatch")
        return {"org_id": "o1", "role": "member"}

    monkeypatch.setattr(orgs, "accept_invite", fake_accept)

    class Body:
        invite_id = "inv12345678"

    with pytest.raises(HTTPException) as ei:
        await org_api.accept_invite(Body(), ("user-1", "other@x.com"))
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_accept_seat_limit(monkeypatch):
    async def fake_accept(invite_id, user_id, user_email, *, seat_limit):
        raise ValueError("seat_limit")

    monkeypatch.setattr(orgs, "accept_invite", fake_accept)

    class Body:
        invite_id = "inv12345678"

    with pytest.raises(HTTPException) as ei:
        await org_api.accept_invite(Body(), ("user-1", "invitee@x.com"))
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_invite_counts_pending(monkeypatch):
    async def fake_plan(uid):
        return "team"

    async def fake_get(uid):
        return {
            "org_id": "o1",
            "owner_user_id": "owner",
            "role": "owner",
            "name": "Team",
        }

    async def fake_count(oid):
        return 4

    async def fake_pending(oid):
        return 1

    monkeypatch.setattr(org_api, "get_user_plan", fake_plan)
    monkeypatch.setattr(orgs, "get_org_for_user", fake_get)
    monkeypatch.setattr(orgs, "member_count", fake_count)
    monkeypatch.setattr(orgs, "pending_invite_count", fake_pending)

    class Body:
        email = "new@x.com"

    with pytest.raises(HTTPException) as ei:
        await org_api.invite_member(Body(), "owner")
    assert ei.value.status_code == 403
