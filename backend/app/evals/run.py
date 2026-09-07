import asyncio
from app.evals.dataset import generate_factual_cases, QUALITATIVE_CASES
from app.evals.scorer import numerical_match, citation_grounded
from app.answer.engine import answer_stream
from app.retrieval.rerank import retrieve

async def _collect_answers(query, ticker):
    """Run the real pipeline; gather streamed text + which chunks were sourced."""
    text, source_ids = "", set()
    async for ev in answer_stream(query, ticker):
        if ev["type"] == "sources":
            source_ids = {s["id"] for s in ev["sources"]}
        elif ev["type"] == "answer":
            text += ev["delta"]
    return text, source_ids

async def run_evals(sample: int | None = None) -> dict:
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
    return {
        "factual_accuracy": round(fact_pass / max(len(factual), 1), 3),
        "factual_n": len(factual),
        "qualitative_accuracy": round(qual_pass / max(len(QUALITATIVE_CASES), 1), 3),
    }

if __name__ == "__main__":
    import json
    print(json.dumps(asyncio.run(run_evals()), indent=2))