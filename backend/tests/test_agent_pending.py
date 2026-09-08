from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.agent import pending
from app.agent.graph import is_advice_like


def test_is_advice_like():
    assert is_advice_like("You should buy AAPL now.") is True
    assert is_advice_like("Revenue grew 12% [cite:c1].") is False
    assert is_advice_like(None) is False


@pytest.mark.asyncio
async def test_create_and_get_pending(monkeypatch):
    store = {}

    class Result:
        def __init__(self, row=None, rowcount=1):
            self._row = row
            self.rowcount = rowcount

        def mappings(self):
            return self

        def first(self):
            return self._row

    class Conn:
        async def execute(self, stmt, params):
            sql = str(stmt)
            if "INSERT INTO agent_pending_runs" in sql:
                store[params["r"]] = {
                    "run_id": params["r"],
                    "user_id": params["u"],
                    "thread_id": params["t"],
                    "query": params["q"],
                    "draft_answer": params["d"],
                    "messages_json": params["m"],
                    "sources_json": params["s"],
                    "series_json": params["ser"],
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc),
                }
                return Result()
            if "SELECT" in sql and "agent_pending_runs" in sql:
                row = store.get(params["r"])
                if not row or row["user_id"] != params["u"]:
                    return Result(None)
                return Result(dict(row))
            return Result()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Engine:
        def begin(self):
            return Conn()

    monkeypatch.setattr(pending, "engine", Engine())
    run_id = await pending.create_pending_run(
        user_id="u1",
        thread_id="research",
        query="q",
        draft_answer="You should buy.",
        messages=[{"role": "user", "content": "q"}],
        sources=[],
        series=None,
    )
    got = await pending.get_pending_run(run_id, "u1")
    assert got["draft_answer"] == "You should buy."
    with pytest.raises(HTTPException) as ei:
        await pending.get_pending_run(run_id, "other")
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_expired_pending(monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    store = {
        "abc": {
            "run_id": "abc",
            "user_id": "u1",
            "thread_id": "research",
            "query": "q",
            "draft_answer": "draft",
            "messages_json": "[]",
            "sources_json": "[]",
            "series_json": None,
            "status": "pending",
            "created_at": old,
        }
    }

    class Result:
        def __init__(self, row=None, rowcount=1):
            self._row = row
            self.rowcount = rowcount

        def mappings(self):
            return self

        def first(self):
            return self._row

    class Conn:
        async def execute(self, stmt, params):
            sql = str(stmt)
            if "SELECT" in sql:
                row = store.get(params["r"])
                if not row or row["user_id"] != params["u"]:
                    return Result(None)
                return Result(dict(row))
            if "UPDATE" in sql:
                store[params["r"]]["status"] = params["s"]
                return Result(rowcount=1)
            return Result()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Engine:
        def begin(self):
            return Conn()

    monkeypatch.setattr(pending, "engine", Engine())
    with pytest.raises(HTTPException) as ei:
        await pending.get_pending_run("abc", "u1")
    assert ei.value.status_code == 410


@pytest.mark.asyncio
async def test_resolve_pending(monkeypatch):
    store = {
        "r1": {"status": "pending", "user_id": "u1"},
    }

    class Result:
        def __init__(self, rowcount=1):
            self.rowcount = rowcount

    class Conn:
        async def execute(self, stmt, params):
            if store.get(params["r"], {}).get("user_id") != params["u"]:
                return Result(0)
            if store[params["r"]]["status"] != "pending":
                return Result(0)
            store[params["r"]]["status"] = params["s"]
            return Result(1)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Engine:
        def begin(self):
            return Conn()

    monkeypatch.setattr(pending, "engine", Engine())
    await pending.resolve_pending("r1", "u1", "approved")
    assert store["r1"]["status"] == "approved"
