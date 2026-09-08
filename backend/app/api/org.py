from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import RequiredUser, RequiredUserEmail, get_user_plan
from app.api.limits import normalize_plan, seat_limit
from app.orgs import store as orgs

router = APIRouter(prefix="/org", tags=["org"])


class InviteBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class AcceptBody(BaseModel):
    invite_id: str = Field(min_length=8, max_length=64)


@router.get("/me")
async def org_me(user_id: RequiredUser):
    plan = normalize_plan(await get_user_plan(user_id))
    org = await orgs.get_org_for_user(user_id)
    if not org:
        return {
            "org": None,
            "plan": plan,
            "seat_limit": seat_limit(plan),
            "members": [],
            "member_count": 0,
            "pending_invites": 0,
        }
    members = await orgs.list_members(org["org_id"])
    pending = await orgs.pending_invite_count(org["org_id"])
    return {
        "org": org,
        "plan": plan,
        "seat_limit": seat_limit(plan),
        "members": members,
        "member_count": len(members),
        "pending_invites": pending,
    }


@router.post("/invite")
async def invite_member(body: InviteBody, user_id: RequiredUser):
    plan = normalize_plan(await get_user_plan(user_id))
    if plan != "team":
        raise HTTPException(403, "Team plan required to invite seats.")
    org = await orgs.get_org_for_user(user_id)
    if not org:
        org = await orgs.ensure_team_org(user_id)
    if org.get("owner_user_id") != user_id and org.get("role") != "owner":
        raise HTTPException(403, "Only the org owner can invite.")
    n = await orgs.member_count(org["org_id"])
    pending = await orgs.pending_invite_count(org["org_id"])
    limit = seat_limit(plan)
    if n + pending >= limit:
        raise HTTPException(
            403, f"Seat limit reached ({limit}), including pending invites."
        )
    return await orgs.create_invite(org["org_id"], body.email, user_id)


@router.post("/accept")
async def accept_invite(body: AcceptBody, claims: RequiredUserEmail):
    user_id, email = claims
    # Only Team orgs invite; enforce Team seat cap atomically on accept.
    limit = seat_limit("team")
    try:
        org = await orgs.accept_invite(
            body.invite_id, user_id, email, seat_limit=limit
        )
    except ValueError as e:
        code = str(e)
        if code == "invite_not_found":
            raise HTTPException(404, "Invite not found or already used.")
        if code == "email_mismatch":
            raise HTTPException(403, "Invite email does not match your account.")
        if code == "email_required":
            raise HTTPException(400, "Account email required to accept invite.")
        if code == "already_in_org":
            raise HTTPException(409, "Already in a team org.")
        if code == "seat_limit":
            raise HTTPException(403, "Seat limit reached.")
        raise HTTPException(400, code)
    return {"org": org}
