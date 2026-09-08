from app.evals.offline import collect_gate_results, run_offline_evals
from app.evals.run import OFFLINE_MIN, evals_passed


def test_offline_evals_all_pass():
    report = run_offline_evals()
    assert report["offline_pass_rate"] >= OFFLINE_MIN, report["offline_failed"]
    assert report["offline_n"] >= 10
    assert evals_passed(report)


def test_each_offline_gate_named():
    results = collect_gate_results()
    names = [r.name for r in results]
    assert len(names) == len(set(names))
    assert any(n.startswith("is_advice_like:") for n in names)
    assert "sanitize_redacts_injection" in names
    assert "usage_from_response_tokens" in names
    assert all(r.ok for r in results), [r for r in results if not r.ok]
