import pytest
from fastapi import HTTPException

from app.api import deps
from app.config import settings


@pytest.mark.asyncio
async def test_optional_user_none_when_auth_not_required(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)
    assert await deps.optional_user(None) is None


@pytest.mark.asyncio
async def test_optional_user_401_when_auth_required(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    with pytest.raises(HTTPException) as ei:
        await deps.optional_user(None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_optional_user_decodes_bearer(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)

    async def fake_create(user_id, email=None):
        return user_id

    monkeypatch.setattr(
        deps,
        "_decode_bearer",
        lambda authorization: {"sub": "user-abc", "email": "a@b.co"},
    )
    monkeypatch.setattr(deps, "get_or_create_user", fake_create)
    assert await deps.optional_user("Bearer fake") == "user-abc"
