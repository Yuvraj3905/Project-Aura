-- Aura schema — migration 0002
-- Allow an intermediate 'in_progress' ticket state for transitions:
--   open -> in_progress -> closed
-- Mounted into the postgres init dir as 02_*.sql so a fresh volume bootstraps it.
-- For an existing volume, apply manually:
--   docker compose exec postgres psql -U aura -d aura -f /docker-entrypoint-initdb.d/02_ticket_in_progress.sql

ALTER TABLE support_tickets DROP CONSTRAINT IF EXISTS support_tickets_status_check;
ALTER TABLE support_tickets
    ADD CONSTRAINT support_tickets_status_check
    CHECK (status IN ('open', 'in_progress', 'closed'));
