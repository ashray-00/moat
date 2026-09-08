"""Tests for Ask streaming usage extraction (no live LLM)."""

from types import SimpleNamespace

from app.answer.engine import _usage_from_stream_chunk


def test_usage_from_stream_chunk_object():
    part = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=20,
            cache_read_input_tokens=5,
        )
    )
    got = _usage_from_stream_chunk(part, "test-model")
    assert got is not None
    assert got["tokens_in"] == 100
    assert got["tokens_out"] == 20
    assert got["cached_in"] == 5
    assert got["model"] == "test-model"
    assert isinstance(got["cost_usd"], float)


def test_usage_from_stream_chunk_missing():
    assert _usage_from_stream_chunk(SimpleNamespace(), "m") is None
