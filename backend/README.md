# Moat backend

```bash
# from repo root
source .venv/bin/activate
# apply schema (once)
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
- Stripe: set `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID_PRO` (or `STRIPE_PRICE_ID`), `STRIPE_PRICE_ID_TEAM`, and webhook secret for Checkout
