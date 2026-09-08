# Security model (deploy checklist)

Moat is a multi-tenant research API over a **shared SEC corpus** with
**per-user entitlements** (plan, coverage adds, org seats). This page is the
ops/security contract — not a red-team novel.

## Authentication

- Supabase JWTs verified via **JWKS** (`ES256`/`RS256`), audience
  `authenticated`, issuer `{SUPABASE_URL}/auth/v1`.
- Production default: **`AUTH_REQUIRED=true`** (also the Settings default).
  `/ask`, agent, universe, billing, org, memory, and admin require Bearer.
- Set `AUTH_REQUIRED=false` only for local demos without login.

## Authorization highlights

| Surface | Rule |
|---------|------|
| Admin (`/admin/*`) | Fail-closed: empty `ADMIN_USER_IDS` → nobody is admin |
| Org invite accept | JWT **email** must match invite email (client email ignored) |
| Org seats | Cap checked on invite (members + pending) and again on accept |
| Team entitlements | Org members inherit owner's **Team** plan for quotas/RPM/coverage |
| Coverage retrieve | Ask/Agent tools only search tickers in `effective_universe(user)` |
| HITL pending runs | Scoped by `(run_id, user_id)` |
| Metrics | Disabled until `METRICS_TOKEN` is set |

## Abuse / cost controls

- **Atomic quota reserve** before LLM work (`usage_log` pending row).
- Free plan: **5 asks/month**, **Agent off** by default (`FREE_AGENT_ENABLED`).
- Daily USD caps from `usage_log.cost_usd` (`DAILY_COST_USD_PER_USER` /
  `DAILY_COST_USD_GLOBAL`); Agent per-run cost + tool-round caps.
- Kill switches: `LLM_ENABLED`, `AGENT_ENABLED`.
- New accounts: disposable-email blocklist + `MAX_SIGNUPS_PER_HOUR` (Postgres).
- Per-plan **RPM**; if `REDIS_URL` is set, Redis is required (fail **503** if
  unreachable — no silent memory fallback across replicas).
- Without Redis, limits are **per process** only — use Redis for multi-instance.
- Generic SSE error messages to clients; full exceptions stay in server logs.
- Answer cache (if enabled) is **keyed by `user_id`**.

## Content safety (defense in depth)

- `input_ok` on Ask/Agent/memory writes.
- `sanitize_retrieved` / memory sanitizers on filing text and session memory.
- Citation structural check (`[cite:`) and Agent advice HITL (Approve/Rewrite).
- Regex guards are not a substitute for product review of advice-shaped answers.

## Observability

- Langfuse only activates when **both** `LANGFUSE_PUBLIC_KEY` and
  `LANGFUSE_SECRET_KEY` are set.
- Ask: root `chain` → nested `retriever` + `generation` (tokens/cost when
  the provider returns stream usage).
- Agent: root `agent` span with status / cost metadata; `flush` after each run.

## Rerank (deploy choice)

- `RERANK_PROVIDER=local` — CrossEncoder weights on the API box (default).
- `RERANK_PROVIDER=cohere` — needs `COHERE_API_KEY` (+ optional model id).
- `RERANK_PROVIDER=none` — skip rerank; hybrid only (lighter box).

## Deploy must-set

1. `AUTH_REQUIRED=true`
2. `SUPABASE_URL` (+ frontend Supabase keys)
3. `FRONTEND_ORIGIN` / `FRONTEND_URL` to your HTTPS origins
4. `DATABASE_URL`; apply [`backend/app/ingest/schema.sql`](../backend/app/ingest/schema.sql)
5. `ADMIN_USER_IDS` = trusted user UUIDs only (or leave empty)
6. `METRICS_TOKEN` strong or unset
7. `REDIS_URL` if running more than one API replica
8. `ANSWER_CACHE_ENABLED=false` unless you need it (already user-scoped)
9. Stripe keys only when you enable checkout/webhooks
10. Run **API + `python -m worker.ingest`** (see `docker-compose.yml`)

## Out of scope here

- Live Stripe webhook URL setup (hosting-specific).
- Hosted reranker swap (local cross-encoder remains the default).

See also: [eval-report.md](eval-report.md), [postmortem.md](postmortem.md).
