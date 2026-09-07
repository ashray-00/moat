CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE companies (
    cik TEXT PRIMARY KEY,
    ticker TEXT UNIQUE,
    name TEXT
);

CREATE TABLE filings (
    id BIGSERIAL PRIMARY KEY,
    cik TEXT REFERENCES companies(cik),
    form TEXT,
    accession TEXT UNIQUE,
    filing_date DATE,
    doc_url TEXT
);

CREATE TABLE chunks (
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

CREATE TABLE facts (
    cik TEXT,
    tag TEXT,
    fy INT,
    period_end DATE,
    val DOUBLE PRECISION,
    form TEXT,
    PRIMARY KEY (cik, tag, fy, period_end)
);

CREATE TABLE answer_cache (
    id BIGSERIAL PRIMARY KEY,
    query TEXT,
    answer TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX answer_cache_emb_idx ON answer_cache USING hnsw (embedding vector_cosine_ops);
