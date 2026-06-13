-- Aura schema — migration 0004
-- Sales-funnel capture: leads (buying signals → follow-up) and orders (purchase intent).
-- Mounted into the postgres init dir as 04_leads_orders.sql for fresh volumes; apply to an
-- existing volume with:  psql "$DATABASE_URL" -f db/migrations/0004_leads_orders.sql

-- leads: a prospect who showed interest and left contact details ------------------
CREATE TABLE IF NOT EXISTS leads (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text,                                 -- optional display name
    email            text NOT NULL,
    product_interest text,                                 -- what they were asking about
    session_id       text,                                 -- Rasa conversation / sender id
    status           text NOT NULL DEFAULT 'new'
                          CHECK (status IN ('new', 'contacted', 'converted', 'closed')),
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);

-- orders: a concrete purchase intent for a specific product ----------------------
CREATE TABLE IF NOT EXISTS orders (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text NOT NULL,
    product     text NOT NULL,                             -- which model they want
    quantity    integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
    session_id  text,
    status      text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'confirmed', 'fulfilled', 'cancelled')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
