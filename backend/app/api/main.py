import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import admin, agent, ask, billing, memory, metrics, org, universe, watchlist
from app.config import settings
from app.db import engine

logger = logging.getLogger(__name__)

app = FastAPI(title="Moat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ask.router)
app.include_router(watchlist.router)
app.include_router(universe.router)
app.include_router(memory.router)
app.include_router(agent.router)
app.include_router(billing.router)
app.include_router(org.router)
app.include_router(admin.router)
app.include_router(metrics.router)


@app.get("/health")
async def health():
    db_ok = False
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        # Surface the class name in Render logs (no secrets).
        logger.exception("health db check failed")
        db_ok = False
    return {"ok": db_ok, "db": db_ok}
