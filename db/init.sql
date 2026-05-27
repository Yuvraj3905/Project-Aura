-- Runs once on first container init (empty data volume).
-- Enables pgvector. Schema tables come in a later phase.
CREATE EXTENSION IF NOT EXISTS vector;
