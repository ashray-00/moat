"""Async SQLAlchemy engine + session.

The engine is lazy: it does not open a connection until first use.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def async_database_url(url: str) -> str:
    """Force the asyncpg driver so plain postgresql:// (Supabase paste) still works."""
    u = (url or "").strip()
    if u.startswith("postgresql+asyncpg://") or u.startswith("postgres+asyncpg://"):
        return u
    if u.startswith("postgresql://"):
        return "postgresql+asyncpg://" + u[len("postgresql://") :]
    if u.startswith("postgres://"):
        return "postgresql+asyncpg://" + u[len("postgres://") :]
    return u


engine = create_async_engine(
    async_database_url(settings.database_url),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
