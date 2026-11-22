


-- FactoryIQ Milestone 3: Agent execution columns on investigations.
-- Adds 'failed' as a valid status and three audit columns.
-- All statements are safe to run multiple times on an existing database.

-- Extend the status constraint to include 'failed'.
-- DROP + ADD is the standard PostgreSQL pattern for altering a CHECK constraint.
ALTER TABLE investigations
    DROP CONSTRAINT IF EXISTS investigations_status_check;

ALTER TABLE investigations
    ADD CONSTRAINT investigations_status_check
    CHECK (status IN ('in_progress','pending_review','approved','rejected','failed'));

-- Agent execution metadata (safe to add repeatedly via IF NOT EXISTS).
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS agent_model       TEXT;
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS agent_error       TEXT;
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS agent_tool_calls  INTEGER DEFAULT 0;
