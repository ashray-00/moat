CREATE EXTENSION IF NOT EXISTS vector;

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
CREATE INDEX chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops);

-- Sparse index
CREATE INDEX chunks_fts_idx ON chunks USING gin (fts);

-- Metadata filter index
CREATE INDEX chunks_ticker_idx ON chunks (ticker);

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

CREATE INDEX answer_cache_emb_idx ON answer_cache USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id TEXT,
    ticker TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS session_summaries (
    user_id TEXT,
    thread_id TEXT,
    summary TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, thread_id)
);

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
)
