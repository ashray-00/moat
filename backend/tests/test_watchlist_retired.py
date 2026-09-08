import pytest
from fastapi import HTTPException

from app.api import watchlist as watchlist_api


@pytest.mark.asyncio
async def test_watchlist_gone():
    with pytest.raises(HTTPException) as ei:
        await watchlist_api.list_watchlist("u1")
    assert ei.value.status_code == 410
