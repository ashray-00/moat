"""Unit tests for DATABASE_URL asyncpg normalization."""

from app.db import async_database_url


def test_async_database_url_adds_asyncpg():
    assert async_database_url(
        "postgresql://user:pass@db.example.com:5432/postgres"
    ).startswith("postgresql+asyncpg://")


def test_async_database_url_keeps_asyncpg():
    u = "postgresql+asyncpg://user:pass@localhost/moat"
    assert async_database_url(u) == u


def test_async_database_url_postgres_scheme():
    assert async_database_url("postgres://u:p@h/db").startswith("postgresql+asyncpg://")
