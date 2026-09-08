from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import RequiredUser
from app.config import settings
from app.db import engine
from app.universe import store as ustore
from sqlalchemy import text

router = APIRouter(prefix="/admin", tags=["admin"])


def _is_admin(user_id: str) -> bool:
    raw = (settings.admin_user_ids or "").strip()
    if not raw:
        return False
    allowed = {p.strip() for p in raw.split(",") if p.strip()}
    return user_id in allowed


async def require_admin(user_id: str) -> None:
    if not _is_admin(user_id):
        raise HTTPException(403, "Admin access required.")


@router.get("/me")
async def admin_me(user_id: RequiredUser):
    return {"admin": _is_admin(user_id)}


@router.get("/companies")
async def admin_companies(user_id: RequiredUser):
    await require_admin(user_id)
    return {"companies": await ustore.list_companies()}


@router.get("/ingest-jobs")
async def admin_jobs(user_id: RequiredUser):
    await require_admin(user_id)
    return {"jobs": await ustore.list_recent_ingest_jobs()}


class ReingestBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


async def _kick_job(job_id: int, ticker: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ingest_jobs SET status='running', started_at=now(), "
                "updated_at=now() WHERE id=:id AND status='pending'"
            ),
            {"id": job_id},
        )
    await ustore.process_ingest_job(
        {"id": job_id, "ticker": ticker, "status": "running"}
    )


@router.post("/reingest")
async def admin_reingest(
    body: ReingestBody,
    user_id: RequiredUser,
    background_tasks: BackgroundTasks,
):
    await require_admin(user_id)
    ticker = body.ticker.strip().upper()
    if not ticker.isalnum():
        raise HTTPException(400, "invalid ticker")
    job_id, created = await ustore.enqueue_ingest_job(ticker)
    if created and job_id is not None:
        background_tasks.add_task(_kick_job, job_id, ticker)
    return {"ticker": ticker, "job_id": job_id, "created": created}
