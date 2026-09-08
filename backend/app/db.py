"""Async SQLAlchemy engine + session.

The engine is lazy: it does not open a connection until first use.
"""

from __future__ import annotations

from urllib.parse import urlparse

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


def _needs_ssl(url: str) -> bool:
    """Supabase and other hosted Postgres require TLS; local docker does not."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return False
    return True


_url = async_database_url(settings.database_url)
_connect_args: dict = {"ssl": True} if _needs_ssl(_url) else {}

engine = create_async_engine(
    _url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
