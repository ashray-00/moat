CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Existing DBs created before Stripe columns existed:
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_customer_id_uidx
    ON users (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    event_id TEXT PRIMARY KEY,
    received_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS companies (
    cik TEXT PRIMARY KEY,
    ticker TEXT UNIQUE,
    name TEXT
);

CREATE TABLE IF NOT EXISTS filings (
    id BIGSERIAL PRIMARY KEY,
    cik TEXT REFERENCES companies(cik),
    form TEXT,
    accession TEXT UNIQUE,
    filing_date DATE,
    doc_url TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    filing_id BIGINT REFERENCES filings(id) ON DELETE CASCADE,
    cik TEXT,
    ticker TEXT,
    section TEXT,
    is_table BOOLEAN DEFAULT FALSE,
    text TEXT,
    tokens INT,
    embedding VECTOR(1536),
    fts tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);

-- Dense index
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops);

-- Sparse index
CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING gin (fts);

-- Metadata filter index
CREATE INDEX IF NOT EXISTS chunks_ticker_idx ON chunks (ticker);

CREATE TABLE IF NOT EXISTS facts (
    cik TEXT,
    tag TEXT,
    fy INT,
    period_end DATE,
    val DOUBLE PRECISION,
    form TEXT,
    PRIMARY KEY (cik, tag, fy, period_end)
);

CREATE TABLE IF NOT EXISTS answer_cache (
    id BIGSERIAL PRIMARY KEY,
    query TEXT,
    answer TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS answer_cache_emb_idx ON answer_cache USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id TEXT,
    ticker TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, ticker)
);

-- Per-user ticker additions beyond DEFAULT_UNIVERSE (Pro/Team).
-- Shared corpus stays in companies/chunks; this table is membership + ingest status only.
CREATE TABLE IF NOT EXISTS user_ticker_adds (
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, ticker)
);

CREATE INDEX IF NOT EXISTS user_ticker_adds_user_status_idx
    ON user_ticker_adds (user_id, status);

CREATE TABLE IF NOT EXISTS session_summaries (
    user_id TEXT,
    thread_id TEXT,
    summary TEXT,
    recent JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, thread_id)
);

-- Existing DBs created before `recent` existed:
ALTER TABLE session_summaries
    ADD COLUMN IF NOT EXISTS recent JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS usage_log (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    model TEXT,
    tokens_in INT,
    tokens_out INT,
    cached_in INT,
    cost_usd DOUBLE PRECISION,
    latency_ms INT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Agent HITL: drafts held for the signed-in user to Approve or Rewrite.
CREATE TABLE IF NOT EXISTS agent_pending_runs (
    run_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    query TEXT NOT NULL,
    draft_answer TEXT NOT NULL,
    messages_json JSONB NOT NULL,
    sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    series_json JSONB,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS agent_pending_runs_user_idx
    ON agent_pending_runs (user_id, status, created_at DESC);
