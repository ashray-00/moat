# Moat backend

```bash
# from repo root
source .venv/bin/activate
# apply schema (once; safe to re-run)
psql "$DATABASE_URL" -f backend/app/ingest/schema.sql   # or use a SQL client

uvicorn app.api.main:app --reload --app-dir backend --port 8000
```

Optional seed:

```bash
cd backend && python -m worker.seed
```

Key flags in root `.env` / `.env.example`:

- `AUTH_REQUIRED=true` — JWT required on research routes
- `FRONTEND_ORIGIN` — CORS allowlist
- Plans: free / pro / team (monthly asks + per-plan RPM). `GET /billing/me` for usage.

## Stripe checklist

1. Create Products **Moat Pro** and **Moat Team** with recurring Prices; copy IDs into `STRIPE_PRICE_ID_PRO` (or legacy `STRIPE_PRICE_ID`) and `STRIPE_PRICE_ID_TEAM`.
2. Set `STRIPE_SECRET_KEY=sk_test_...` (test) or live key.
3. **Local webhooks:** `stripe listen --forward-to localhost:8000/billing/webhook` and set `STRIPE_WEBHOOK_SECRET` to the printed `whsec_...`.
4. **Deployed:** Dashboard webhook → `https://<api>/billing/webhook` for `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`.
5. Enable Customer Portal (cancel/update) in Stripe Dashboard — Account → Manage billing uses `POST /billing/portal`.

Without the webhook forwarder, Checkout can succeed while `users.plan` stays free until Stripe delivers the event.

## Coverage (tickers)

- Free users see the fixed default universe (seed list; override with `MOAT_DEFAULT_UNIVERSE`).
- Pro/Team can add custom tickers (async SEC ingest into the **shared** DB — skipped if already ingested) and remove only their adds.
- Apply schema (includes `ingest_jobs`, orgs): `psql "$DATABASE_URL" -f backend/app/ingest/schema.sql`
- Run ingest worker alongside API when adds need durable processing: `python -m worker.ingest`

## Team seats

- Team plan creates an org on subscription; owner invites via `POST /org/invite` (seat_limit 5).
- Accept with `POST /org/accept`.

## Admin

- Set `ADMIN_USER_IDS` to comma-separated user ids. Endpoints under `/admin`.

## Rate limits

- Optional `REDIS_URL` for shared RPM across workers; otherwise in-process.
  When `REDIS_URL` is set but Redis is down, API returns **503** (fail closed).
- Free: Agent off by default (`FREE_AGENT_ENABLED`). Daily USD caps
  (`DAILY_COST_USD_*`), Agent round/cost caps, disposable-email + signup-rate
  gates — see root `.env.example` and [docs/security.md](../docs/security.md).

## Observability

- Set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` to enable tracing.
- Ask opens a `chain` span with nested `retriever` + `generation`.
- Agent opens an `agent` span; flush on completion.
- Without keys, tracing is a no-op (API still works).

## Rerank

| `RERANK_PROVIDER` | Needs | Notes |
|-------------------|-------|-------|
| `cohere` (Docker default) | `COHERE_API_KEY` | Best for slim hosts (Render free) |
| `none` | — | Hybrid retrieval only |
| `local` | `pip install -e "backend[local-rerank]"` | Downloads CrossEncoder; heavy RAM |

## Agent checkpoint

- `AGENT_CHECKPOINT=true` (default) uses LangGraph **AsyncPostgresSaver** on
  the same `DATABASE_URL` (creates checkpoint tables on first use).
- Approve/Rewrite HITL still uses `agent_pending_runs`.

## Safety

- Queries: `input_ok` on Ask/Agent (injection + length).
- Filings/tools: `sanitize_retrieved` on excerpts.
- Memory: sanitized when re-injected into Ask/Agent; `PUT /memory` rejects injection-like payloads.
- Agent HITL: `is_advice_like` on drafts; Ask adds a disclaimer when the query solicits advice.
- Soft citation check on agent answers that used filing sources.

## Evals & quality gates

Every PR runs **offline** gates (advice HITL, sanitize, citation grounding, numerical match, usage/cost helpers) via unit CI — no DB or LLM keys required:

```bash
cd backend && python -m app.evals.run --offline-only
# or: pytest -q tests/test_evals_offline.py
```

Live Ask + retrieval evals (needs ingested DB + API keys) fail the workflow when below floors (`factual >= 0.70`, `qualitative == 1.0`, offline `== 1.0`):

```bash
cd backend && python -m app.evals.run --sample=40
```

Trigger the full live job with **Actions → eval-gate → Run workflow**.
