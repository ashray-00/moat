# Moat frontend

Next.js app for equity research over SEC filings. Access is passwordless via Supabase magic link.

## Setup

1. Copy `.env.local.example` to `.env.local`
2. Set `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
3. In Supabase Auth, enable Email (magic link / OTP) and add redirect URL `http://localhost:3000/auth/callback`
4. Ensure the API has `AUTH_REQUIRED=true` and matching `SUPABASE_URL` / `FRONTEND_ORIGIN`

```bash
npm install
npm run dev
```

Signed-out users only see Sign in / Create account. Ask, Agent, and Coverage require a session.
