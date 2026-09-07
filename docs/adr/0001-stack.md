# ADR 0001 - Core stack for Moat

## Context
Equity-reasearch assistant over SEC filings. Solo build, must deploy, must be 
cheap to run, must be evaluable against ground truth.

## Decisions
- **pgvector over a dedicated vector DB.** Corpus is <10M vectors. One datastore
  (Postgres) reduces operational surface. Revisit if we exceed ~10M vectors or
  need multi-region low-latency search.
- **Hybrid retrieval + cross-encoder rerank.** FIling mix exact terms (GAAP tags,
  tickers) with prose; pure-dense loses the former, pure-sparse loses paraphrase.
- **LiteLLM gateway.** Provider independence + native cost tracking. Cost is the
  most underrated 2026 skill; the gateway is where we exercise it.
- **LangGraph for the agent.** Need durable state + human-in-the-loop for any 
  action that could mislead (e.g. glagged "advice-like" answers).
- **Ground-truth evals from XBRL.** The reason we chose finance: we can compute a
  real factual-accuracy number and gate deploys on it.

## Consequences
- We are re-embedding when we change the embedding model.
- Local reranker adds ~80ms/query but $0 per call and no vendor lock.