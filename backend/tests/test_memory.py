import pytest

from app.memory import store


@pytest.mark.asyncio
async def test_remember_turn_compacts_when_over_cap(monkeypatch):
    state = {"summary": "Prior focus on AAPL margins.", "recent": []}

    async def fake_load(user_id, thread_id):
        return {"summary": state["summary"], "recent": list(state["recent"])}

    async def fake_save(user_id, thread_id, *, summary, recent):
        state["summary"] = summary
        state["recent"] = list(recent)

    async def fake_compact(summary, old_turns):
        return f"{summary} | compacted {len(old_turns)} msgs"

    monkeypatch.setattr(store, "load_memory", fake_load)
    monkeypatch.setattr(store, "_save_memory", fake_save)
    monkeypatch.setattr(store, "_compact", fake_compact)

    # WORKING_MAX is 8 messages; push past it.
    for i in range(5):
        await store.remember_turn("u", "t", f"q{i}", f"a{i}")

    assert len(state["recent"]) <= store.WORKING_KEEP
    assert "compacted" in (state["summary"] or "")


@pytest.mark.asyncio
async def test_remember_turn_keeps_buffer_if_compact_fails(monkeypatch):
    state = {"summary": None, "recent": []}

    async def fake_load(user_id, thread_id):
        return {"summary": state["summary"], "recent": list(state["recent"])}

    async def fake_save(user_id, thread_id, *, summary, recent):
        state["summary"] = summary
        state["recent"] = list(recent)

    async def boom(summary, old_turns):
        raise RuntimeError("llm down")

    monkeypatch.setattr(store, "load_memory", fake_load)
    monkeypatch.setattr(store, "_save_memory", fake_save)
    monkeypatch.setattr(store, "_compact", boom)

    for i in range(5):
        await store.remember_turn("u", "t", f"q{i}", f"a{i}")

    assert len(state["recent"]) == store.WORKING_KEEP
    assert state["summary"] is None
