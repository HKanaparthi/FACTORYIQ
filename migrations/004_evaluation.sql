-- FactoryIQ Milestone 5: Evaluation Harness tables
-- All statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS for idempotency.
-- Ground truth is separated from public scenario definitions by design.

-- ---------------------------------------------------------------------------
-- eval_scenarios: public scenario metadata visible to any authenticated user.
-- Ground-truth labels are stored ONLY in eval_ground_truth (never here).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_scenarios (
    scenario_id       TEXT        PRIMARY KEY,
    version           TEXT        NOT NULL DEFAULT '1.0',
    name              TEXT        NOT NULL,
    category          TEXT        NOT NULL
        CHECK (category IN (
            'equipment_fault', 'evidence_quality', 'connectivity',
            'investigation_failure', 'safety_ambiguity', 'four_condition'
        )),
    asset_id          TEXT        NOT NULL,  -- asset under investigation
    evidence_condition TEXT       NOT NULL,  -- NOMINAL | NOMINAL_FAULT | DEGRADED | DEGRADED_MISSING | CONTRADICTORY | WRONG_ASSET
    description       TEXT        NOT NULL,  -- safe public description (no fault labels)
    fault_config      JSONB       NOT NULL DEFAULT '{}',
    expected_behavior JSONB       NOT NULL DEFAULT '{}',
    seed              BIGINT      NOT NULL DEFAULT 42,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- eval_ground_truth: hidden from agent. Only the evaluator reads this AFTER
-- an investigation is finalized. Never exposed via MCP tools or public APIs.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_ground_truth (
    scenario_id                    TEXT    PRIMARY KEY REFERENCES eval_scenarios(scenario_id),
    true_root_cause                TEXT    NOT NULL,
    injected_fault_type            TEXT,
    acceptable_conclusion_patterns JSONB   NOT NULL DEFAULT '[]',  -- regex strings
    negative_patterns              JSONB   NOT NULL DEFAULT '[]',  -- must NOT appear
    uncertainty_required           BOOLEAN NOT NULL DEFAULT FALSE,
    fault_expected                 BOOLEAN NOT NULL DEFAULT FALSE,
    evaluation_notes               TEXT
);

-- ---------------------------------------------------------------------------
-- eval_runs: one record per benchmark session
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    adapter_type         TEXT        NOT NULL DEFAULT 'scripted',
    trial_count          INT         NOT NULL DEFAULT 1,
    status               TEXT        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','cancelled')),
    scenario_ids         TEXT[],                      -- NULL means all scenarios
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_message        TEXT,
    total_scenarios      INT,
    completed_scenarios  INT         NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- eval_run_scenarios: one record per (run × scenario × trial)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_run_scenarios (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID        NOT NULL REFERENCES eval_runs(run_id),
    scenario_id      TEXT        NOT NULL REFERENCES eval_scenarios(scenario_id),
    trial_num        INT         NOT NULL DEFAULT 1,
    investigation_id UUID        REFERENCES investigations(investigation_id),
    status           TEXT        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','skipped')),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    error_message    TEXT
);

-- ---------------------------------------------------------------------------
-- eval_results: scoring results produced by the evaluation engine
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_results (
    result_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_scenario_id     UUID        NOT NULL UNIQUE REFERENCES eval_run_scenarios(id),
    diagnostic_verdict  TEXT        -- correct|incorrect|acceptable_alt|uncertain_correct|non_evaluable
        CHECK (diagnostic_verdict IN (
            'correct','incorrect','acceptable_alt','uncertain_correct','non_evaluable', NULL
        )),
    evidence_grounded   BOOLEAN,
    uncertainty_handled BOOLEAN,
    tool_use_ok         BOOLEAN,
    completed           BOOLEAN,
    score_detail        JSONB       NOT NULL DEFAULT '{}',
    failure_reason      TEXT,
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS eval_run_scenarios_run_id ON eval_run_scenarios(run_id);
CREATE INDEX IF NOT EXISTS eval_results_rsid ON eval_results(run_scenario_id);
