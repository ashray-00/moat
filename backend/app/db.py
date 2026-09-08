"""Async SQLAlchemy engine + session.

The engine is lazy: it does not open a connection until first use.
"""

from __future__ import annotations

import ssl
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


def _uses_pgbouncer(url: str) -> bool:
    """Supabase pooler / PgBouncer needs asyncpg statement cache disabled."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port == 6543:
        return True
    return "pooler.supabase.com" in host


def remote_ssl_context() -> ssl.SSLContext:
    """TLS encrypt without CA hostname checks.

    Matches libpq ``sslmode=require``. Supabase pooler often presents a chain
    that fails default verification (self-signed intermediate).
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def engine_connect_args(url: str) -> dict:
    args: dict = {}
    if _needs_ssl(url):
        args["ssl"] = remote_ssl_context()
    if _uses_pgbouncer(url):
        args["statement_cache_size"] = 0
    return args


_url = async_database_url(settings.database_url)

engine = create_async_engine(
    _url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args=engine_connect_args(_url),
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
