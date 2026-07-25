-- Aura schema — migration 0001
-- Mounted into the postgres init dir as 01_schema.sql, so a fresh volume bootstraps
-- the full schema. Requires the `vector` extension (created by 00_init.sql first).
--
-- Not created here (managed at runtime by their owners):
--   Rasa SQLAlchemyTrackerStore tables — created by Rasa on first run
--
-- Job queue (process_document) lives in Redis via BullMQ, not Postgres — see
-- web/lib/queue.ts.

-- documents: one row per uploaded source file ------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    filename     text        NOT NULL,   -- original client filename (display only)
    storage_path text        NOT NULL,   -- basename under the upload root (e.g. "<id>.pdf")
    mime_type    text        NOT NULL,
    status      text        NOT NULL DEFAULT 'uploaded'
                            CHECK (status IN ('uploaded', 'processing', 'ready', 'failed')),
    summary     text,                          -- doc-level contextual summary (set when ready)
    n_chunks    integer     NOT NULL DEFAULT 0,
    error       text,                          -- failure reason (set when failed)
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status);

-- chunks: contextualized, embedded pieces of a document --------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id            uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    ordinal                integer NOT NULL,           -- position within the document
    content                text    NOT NULL,           -- raw chunk text
    contextualized_content text    NOT NULL,           -- doc summary + content (what we embed)
    token_count            integer NOT NULL DEFAULT 0,
    embedding              vector(384) NOT NULL,        -- BAAI/bge-small-en-v1.5 = 384 dims
    created_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, ordinal)
);

-- HNSW index for cosine similarity search over embeddings.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks (document_id);

-- support_tickets: collected by the Rasa ticket form -----------------------------
CREATE TABLE IF NOT EXISTS support_tickets (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text NOT NULL,
    subject     text,
    description text NOT NULL,
    session_id  text,                                  -- Rasa conversation / sender id
    status      text NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open', 'closed')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- keep documents.updated_at fresh on every update --------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
