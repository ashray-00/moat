from fastapi import HTTPException

from app.api.ratelimit import _hits, check_rate_limit
from app.config import settings


def setup_function():
    _hits.clear()
    # Keep default available for anonymous path tests
    settings.rate_limit_per_minute = 30


def test_rate_limit_allows_under_cap():
    for _ in range(3):
        check_rate_limit("u1", limit=3)


def test_rate_limit_blocks_over_cap():
    for _ in range(3):
        check_rate_limit("u2", limit=3)
    try:
        check_rate_limit("u2", limit=3)
        assert False, "expected 429"
    except HTTPException as e:
        assert e.status_code == 429


def test_rate_limit_default_uses_settings(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    check_rate_limit("anon")
    check_rate_limit("anon")
    try:
        check_rate_limit("anon")
        assert False, "expected 429"
    except HTTPException as e:
        assert e.status_code == 429


def test_rate_limit_disabled_when_zero():
    for _ in range(50):
        check_rate_limit("unlimited", limit=0)
