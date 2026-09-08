from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import RequiredUser

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

_GONE = (
    "Watchlist is retired. Use GET/POST/DELETE /universe for coverage."
)


class WatchlistBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


@router.get("")
async def list_watchlist(user_id: RequiredUser):
    raise HTTPException(410, _GONE)


@router.post("")
async def add_ticker(body: WatchlistBody, user_id: RequiredUser):
    raise HTTPException(410, _GONE)


@router.delete("/{ticker}")
async def delete_ticker(ticker: str, user_id: RequiredUser):
    raise HTTPException(410, _GONE)
