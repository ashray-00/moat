"""Unit tests for observability helpers (no live Langfuse)."""

from app.obs import get_langfuse, span_update, trace_span
from app.agent.checkpoint import checkpoint_dsn, thread_config
from app.config import settings


def test_get_langfuse_none_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")
    # reset cache
    import app.obs as obs

    monkeypatch.setattr(obs, "_langfuse_tried", False)
    monkeypatch.setattr(obs, "_langfuse", None)
    assert get_langfuse() is None


def test_trace_span_noop_without_client(monkeypatch):
    import app.obs as obs

    monkeypatch.setattr(obs, "get_langfuse", lambda: None)
    with trace_span("ask", as_type="chain", input={"q": 1}) as span:
        assert span is None
        span_update(span, output={"ok": True})  # no-op


def test_checkpoint_dsn_strips_asyncpg(monkeypatch):
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+asyncpg://u:p@localhost:5432/moat",
    )
    assert checkpoint_dsn().startswith("postgresql://")
    assert "+asyncpg" not in checkpoint_dsn()


def test_thread_config_scopes_user():
    cfg = thread_config("user-1", "desk")
    assert cfg["configurable"]["thread_id"] == "user-1:desk"
    assert cfg["recursion_limit"] >= 4
