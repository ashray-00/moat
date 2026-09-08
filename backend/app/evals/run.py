import asyncio
import sys

from app.evals.dataset import QUALITATIVE_CASES, generate_factual_cases
from app.evals.offline import run_offline_evals
from app.evals.scorer import citation_grounded, numerical_match
from app.answer.engine import answer_stream
from app.retrieval.rerank import retrieve

# Live pipeline floors — offline gates must be perfect (1.0).
FACTUAL_MIN = 0.70
QUALITATIVE_MIN = 1.0
OFFLINE_MIN = 1.0


async def _collect_answers(query, ticker):
    """Run the real pipeline; gather streamed text + which chunks were sourced."""
    text, source_ids = "", set()
    async for ev in answer_stream(query, ticker):
        if ev["type"] == "sources":
            source_ids = {s["id"] for s in ev["sources"]}
        elif ev["type"] == "answer":
            text += ev["delta"]
    return text, source_ids


async def run_evals(sample: int | None = None, *, live: bool = True) -> dict:
    """Run offline gates always; optionally live Ask/retrieval evals.

    `live=False` is for CI unit jobs (no DB/LLM). Full eval-gate sets live=True.
    """
    report: dict = run_offline_evals()
    if not live:
        return report

    factual = await generate_factual_cases()
    if sample:
        factual = factual[:sample]
    fact_pass = 0
    for c in factual:
        ans, src = await _collect_answers(c["query"], c["ticker"])
        grounded, _, _ = citation_grounded(ans, src)
        if numerical_match(c["expected_number"], ans) and grounded:
            fact_pass += 1
    qual_pass = 0
    for c in QUALITATIVE_CASES:
        got = await retrieve(c["query"], c["ticker"], top_k=5)
        if any(c["must_retrieve_section"].lower() in g["section"].lower() for g in got):
            qual_pass += 1
    report.update(
        {
            "factual_accuracy": round(fact_pass / max(len(factual), 1), 3),
            "factual_n": len(factual),
            "qualitative_accuracy": round(
                qual_pass / max(len(QUALITATIVE_CASES), 1), 3
            ),
            "qualitative_n": len(QUALITATIVE_CASES),
        }
    )
    return report


def evals_passed(report: dict) -> bool:
    """True when every configured gate clears its floor."""
    if report.get("offline_pass_rate", 0) < OFFLINE_MIN:
        return False
    if "factual_accuracy" in report and report["factual_accuracy"] < FACTUAL_MIN:
        return False
    if (
        "qualitative_accuracy" in report
        and report["qualitative_accuracy"] < QUALITATIVE_MIN
    ):
        return False
    return True


if __name__ == "__main__":
    import json

    live = "--offline-only" not in sys.argv
    sample = 40
    for arg in sys.argv[1:]:
        if arg.startswith("--sample="):
            sample = int(arg.split("=", 1)[1])
    report = asyncio.run(run_evals(sample=sample if live else None, live=live))
    print(json.dumps(report, indent=2))
    if not evals_passed(report):
        print("EVAL GATE FAILED", file=sys.stderr)
        sys.exit(1)
    print("EVAL GATE PASSED", file=sys.stderr)
