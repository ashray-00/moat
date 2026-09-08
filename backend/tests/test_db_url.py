"""Unit tests for DATABASE_URL asyncpg normalization and SSL heuristics."""

from app.db import _needs_ssl, async_database_url


def test_async_database_url_adds_asyncpg():
    assert async_database_url(
        "postgresql://user:pass@db.example.com:5432/postgres"
    ).startswith("postgresql+asyncpg://")


def test_async_database_url_keeps_asyncpg():
    u = "postgresql+asyncpg://user:pass@localhost/moat"
    assert async_database_url(u) == u


def test_async_database_url_postgres_scheme():
    assert async_database_url("postgres://u:p@h/db").startswith("postgresql+asyncpg://")


def test_needs_ssl_remote_and_local():
    assert _needs_ssl("postgresql+asyncpg://u:p@db.xxx.supabase.co:5432/postgres")
    assert not _needs_ssl("postgresql+asyncpg://u:p@127.0.0.1:5433/moat")
    assert not _needs_ssl("postgresql+asyncpg://u:p@localhost/moat")
