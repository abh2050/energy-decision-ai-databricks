-- Lakebase (PostgreSQL) operational state. PRD section 5.
-- Each decision run links dataset hash, model version, tariff and battery assumptions,
-- optimizer settings, prompt versions, and MLflow run and trace IDs.
-- Column order and names must match src/edip/store/models.py (checked by tests).

CREATE SCHEMA IF NOT EXISTS edip;

CREATE TABLE IF NOT EXISTS edip.scenarios (
    scenario_id      TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    description      TEXT,
    settings         JSONB NOT NULL,
    settings_hash    TEXT NOT NULL,
    created_by_role  TEXT NOT NULL CHECK (created_by_role IN ('operator', 'viewer', 'system')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS edip.decision_runs (
    run_id               TEXT PRIMARY KEY,
    scenario_id          TEXT NOT NULL REFERENCES edip.scenarios (scenario_id),
    status               TEXT NOT NULL CHECK (status IN (
                             'requested', 'planning_proposed', 'operator_confirmed',
                             'forecasted', 'optimized', 'settled', 'risk_reviewed',
                             'recommended', 'decided', 'failed')),
    dataset_hash         TEXT NOT NULL,
    model_version        TEXT NOT NULL,
    tariff_hash          TEXT NOT NULL,
    battery_hash         TEXT NOT NULL,
    optimizer_settings   JSONB NOT NULL,
    prompt_versions      JSONB NOT NULL,
    mlflow_run_id        TEXT,
    mlflow_trace_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS edip.checkpoints (
    checkpoint_id    TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES edip.decision_runs (run_id),
    step             TEXT NOT NULL,
    payload          JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS edip.approvals (
    approval_id      TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES edip.decision_runs (run_id),
    decision         TEXT NOT NULL CHECK (decision IN ('approve', 'revise', 'reject')),
    actor_role       TEXT NOT NULL CHECK (actor_role = 'operator'),
    actor_hash       TEXT NOT NULL,
    comment          TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS edip.agent_calls (
    call_id            TEXT PRIMARY KEY,
    run_id             TEXT NOT NULL REFERENCES edip.decision_runs (run_id),
    agent              TEXT NOT NULL CHECK (agent IN ('planning', 'risk', 'business')),
    endpoint           TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN (
                           'valid', 'invalid', 'timeout', 'error', 'fallback')),
    latency_ms         INTEGER CHECK (latency_ms >= 0),
    prompt_tokens      INTEGER CHECK (prompt_tokens >= 0),
    completion_tokens  INTEGER CHECK (completion_tokens >= 0),
    mlflow_trace_id    TEXT,
    error_type         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, agent)
);

CREATE INDEX IF NOT EXISTS decision_runs_scenario_idx ON edip.decision_runs (scenario_id);
CREATE INDEX IF NOT EXISTS checkpoints_run_idx ON edip.checkpoints (run_id);
CREATE INDEX IF NOT EXISTS approvals_run_idx ON edip.approvals (run_id);
