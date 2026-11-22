-- FactoryIQ Milestone 2: MCP Server tables
-- All CREATE statements use IF NOT EXISTS for idempotent startup execution.
-- pgcrypto is already installed via 001_initial.sql (runs at DB init as superuser).

-- ---------------------------------------------------------------------------
-- investigations: one record per AI investigation session
-- status transitions: in_progress → pending_review (agent calls flag_for_review)
--                     pending_review → approved | rejected (human action via API)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id            TEXT        NOT NULL,
    trigger_alarm_id    UUID        REFERENCES alarms(alarm_id),
    status              TEXT        NOT NULL DEFAULT 'in_progress'
                            CHECK (status IN ('in_progress','pending_review','approved','rejected')),
    finding_text        TEXT,
    evidence_summary    JSONB,
    alt_hypotheses      JSONB,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    is_simulated        BOOLEAN     NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------------
-- evidence_items: audit log of every MCP tool call within an investigation
-- tool_inputs / tool_output stored as JSONB for full auditability.
-- evidence_tier mirrors the classification defined in PROPOSAL.md.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID        NOT NULL REFERENCES investigations(investigation_id),
    sequence_num        INTEGER     NOT NULL,
    tool_name           TEXT        NOT NULL,
    tool_inputs         JSONB       NOT NULL,
    tool_output         JSONB       NOT NULL,
    evidence_tier       TEXT        NOT NULL
                            CHECK (evidence_tier IN (
                                'CONFIRMED_OBSERVATION',
                                'STATISTICAL_SIGNAL',
                                'CORROBORATING_EVIDENCE',
                                'WEAK_SIGNAL',
                                'INSUFFICIENT_DATA'
                            )),
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    citation_text       TEXT
);

CREATE INDEX IF NOT EXISTS evidence_items_inv
    ON evidence_items (investigation_id, sequence_num);

-- ---------------------------------------------------------------------------
-- equipment_docs: illustrative equipment documentation corpus
-- Used by query_equipment_docs for keyword-based retrieval (Milestone 2).
-- Milestone 6 adds pgvector embeddings via ALTER TABLE ... ADD COLUMN.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equipment_docs (
    doc_id      UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_type  TEXT    NOT NULL,       -- PUMP, MOTOR, CONVEYOR, FILL, GENERAL
    doc_type    TEXT    NOT NULL,       -- MAINTENANCE_GUIDE, FAULT_REFERENCE, ANALYSIS_GUIDE
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    keywords    TEXT[]  NOT NULL DEFAULT '{}',
    source_ref  TEXT    NOT NULL        -- citation label shown to agent and human reviewer
);
