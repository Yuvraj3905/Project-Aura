-- Aura schema — migration 0005
-- Phase 2 retrieval quality: full-text search column for hybrid (BM25+vector) retrieval,
-- and a semantic answer cache keyed by query embedding.
-- Fresh volume: mounted as 05_hybrid_semantic.sql. Existing volume, apply with:
--   docker exec -i aura-postgres psql -U aura -d aura < db/migrations/0005_hybrid_semantic.sql

-- Full-text search vector over chunk content (STORED generated → backfills existing rows
-- and stays in sync on write). Used by the lexical half of hybrid retrieval.
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv ON chunks USING gin (content_tsv);

-- Semantic answer cache: a new query whose embedding is near a previously answered
-- query (same scope) reuses that answer instead of calling the LLM again.
CREATE TABLE IF NOT EXISTS answer_cache_semantic (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    query           text        NOT NULL,
    query_embedding vector(384) NOT NULL,        -- BAAI/bge-small-en-v1.5
    scope_key       text        NOT NULL,        -- "{top_k}:{sorted doc ids | *}"
    answer          jsonb       NOT NULL,         -- full result dict (answer, citations, tokens)
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_answer_cache_semantic_embedding
    ON answer_cache_semantic USING hnsw (query_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_answer_cache_semantic_scope
    ON answer_cache_semantic (scope_key);
