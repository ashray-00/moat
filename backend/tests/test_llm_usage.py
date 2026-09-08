from types import SimpleNamespace

from app.gateway.usage import merge_usage, usage_from_response


def test_usage_from_response_extracts_tokens():
    resp = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=500,
            completion_tokens=40,
            cache_read_input_tokens=50,
        )
    )
    piece = usage_from_response(resp, "anthropic/claude-sonnet-4")
    assert piece["tokens_in"] == 500
    assert piece["tokens_out"] == 40
    assert piece["cached_in"] == 50
    assert piece["model"] == "anthropic/claude-sonnet-4"
    assert isinstance(piece["cost_usd"], float)


def test_usage_from_response_missing_usage():
    piece = usage_from_response(SimpleNamespace(usage=None), "m")
    assert piece == {
        "tokens_in": 0,
        "tokens_out": 0,
        "cached_in": 0,
        "cost_usd": 0.0,
        "model": "m",
    }


def test_merge_usage_sums_calls():
    acc = {
        "tokens_in": 0,
        "tokens_out": 0,
        "cached_in": 0,
        "cost_usd": 0.0,
        "model": "",
    }
    merge_usage(
        acc,
        {
            "tokens_in": 10,
            "tokens_out": 2,
            "cached_in": 1,
            "cost_usd": 0.01,
            "model": "a",
        },
    )
    merge_usage(
        acc,
        {
            "tokens_in": 5,
            "tokens_out": 3,
            "cached_in": 0,
            "cost_usd": 0.02,
            "model": "b",
        },
    )
    assert acc["tokens_in"] == 15
    assert acc["tokens_out"] == 5
    assert acc["cached_in"] == 1
    assert abs(acc["cost_usd"] - 0.03) < 1e-9
    assert acc["model"] == "b"
