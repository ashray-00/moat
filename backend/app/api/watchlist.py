from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import RequiredUser
from app.memory.store import add_to_watchlist, get_watchlist, remove_from_watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


@router.get("")
async def list_watchlist(user_id: RequiredUser):
    return {"tickers": await get_watchlist(user_id)}


@router.post("")
async def add_ticker(body: WatchlistBody, user_id: RequiredUser):
    ticker = body.ticker.strip().upper()
    if not ticker.isalnum():
        raise HTTPException(400, "invalid ticker")
    await add_to_watchlist(user_id, ticker)
    return {"tickers": await get_watchlist(user_id)}


@router.delete("/{ticker}")
async def delete_ticker(ticker: str, user_id: RequiredUser):
    await remove_from_watchlist(user_id, ticker.strip().upper())
    return {"tickers": await get_watchlist(user_id)}
