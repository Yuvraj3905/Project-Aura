-- Aura schema — migration 0006
-- Per-product KB routing: tag each document with a product so unscoped queries can be
-- restricted to the deployment's primary product instead of the whole (mixed) KB.
-- Fresh volume: mounted as 06_document_product.sql. Existing volume:
--   docker exec -i aura-postgres psql -U aura -d aura < db/migrations/0006_document_product.sql

ALTER TABLE documents ADD COLUMN IF NOT EXISTS product text;   -- e.g. "Samsung Galaxy Watch"

CREATE INDEX IF NOT EXISTS idx_documents_product ON documents (product);
