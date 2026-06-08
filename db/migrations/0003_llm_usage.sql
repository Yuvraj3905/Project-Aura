-- Aura schema — migration 0003
-- Per-call LLM usage log. Powers the dashboard's "LLM usage & cost" analytics:
-- token totals, latency, cache hit rate, and the equivalent ChatGPT/OpenAI bill.
-- Mounted into the postgres init dir as 03_*.sql (fresh-volume bootstrap).
-- Existing volume: apply manually:
--   docker compose exec postgres psql -U aura -d aura -f /docker-entrypoint-initdb.d/03_llm_usage.sql

CREATE TABLE IF NOT EXISTS llm_usage (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind              text        NOT NULL,            -- 'answer' | 'summarize'
    model             text        NOT NULL,            -- ollama model tag at call time
    prompt_tokens     integer     NOT NULL DEFAULT 0,  -- input tokens (prompt_eval_count)
    completion_tokens integer     NOT NULL DEFAULT 0,  -- output tokens (eval_count)
    total_tokens      integer     NOT NULL DEFAULT 0,  -- prompt + completion
    duration_ms       integer     NOT NULL DEFAULT 0,  -- wall-clock for the call
    cached            boolean     NOT NULL DEFAULT false, -- true = served from cache, no model call
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage (created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_cached ON llm_usage (cached);
