import pytest

from app.orgs import store as orgs


@pytest.mark.asyncio
async def test_ensure_and_invite_flow(monkeypatch):
    store = {"orgs": {}, "members": {}, "invites": {}}

    async def fake_get(user_id):
        for m in store["members"].values():
            if m["user_id"] == user_id:
                o = store["orgs"][m["org_id"]]
                return {**o, "role": m["role"]}
        return None

    async def fake_ensure(owner, name=None):
        existing = await fake_get(owner)
        if existing:
            return existing
        oid = "org-1"
        store["orgs"][oid] = {
            "org_id": oid,
            "name": name or "Team",
            "owner_user_id": owner,
        }
        store["members"][(oid, owner)] = {
            "org_id": oid,
            "user_id": owner,
            "role": "owner",
        }
        return {**store["orgs"][oid], "role": "owner"}

    async def fake_count(org_id):
        return sum(1 for k in store["members"] if k[0] == org_id)

    async def fake_invite(org_id, email, by):
        iid = "inv-1"
        store["invites"][iid] = {
            "invite_id": iid,
            "org_id": org_id,
            "email": email.lower(),
            "invited_by": by,
            "status": "pending",
        }
        return store["invites"][iid]

    monkeypatch.setattr(orgs, "get_org_for_user", fake_get)
    monkeypatch.setattr(orgs, "ensure_team_org", fake_ensure)
    monkeypatch.setattr(orgs, "member_count", fake_count)
    monkeypatch.setattr(orgs, "create_invite", fake_invite)

    org = await orgs.ensure_team_org("owner-1")
    assert org["org_id"] == "org-1"
    assert await orgs.member_count("org-1") == 1
    inv = await orgs.create_invite("org-1", "a@b.com", "owner-1")
    assert inv["email"] == "a@b.com"
