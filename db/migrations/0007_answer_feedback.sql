-- Aura schema — migration 0007
-- Answer feedback: a 👍/👎 per grounded answer, so the dashboard becomes a quality signal
-- (not just a cost meter). Mounted as 07_answer_feedback.sql for fresh volumes; apply to an
-- existing volume with:  psql "$DATABASE_URL" -f db/migrations/0007_answer_feedback.sql

CREATE TABLE IF NOT EXISTS answer_feedback (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  text,                                  -- Rasa conversation / sender id
    query       text NOT NULL,                         -- the question that was answered
    answer      text,                                  -- snippet of the answer rated (for context)
    rating      text NOT NULL CHECK (rating IN ('up', 'down')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_answer_feedback_rating ON answer_feedback (rating);
