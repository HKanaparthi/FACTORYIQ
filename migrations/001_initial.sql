-- FactoryIQ Milestone 1: Initial Schema
-- Requires TimescaleDB and pgvector extensions

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- telemetry: raw ingested sensor readings
-- One-source rule: source = MQTT_SPARKPLUG during Milestone 1.
-- opc_quality_code: device-reported OPC UA status code (Good=0, Bad=0x80000000, Uncertain=0x40000000)
-- freshness_status: inferred by ingestion service based on elapsed time since last update
--                   (a tag can be opc_quality_label=Good but freshness_status=STALE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry (
    asset_id            TEXT        NOT NULL,
    tag_name            TEXT        NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL,
    value               DOUBLE PRECISION,
    opc_quality_code    BIGINT      NOT NULL,
    opc_quality_label   TEXT        NOT NULL CHECK (opc_quality_label IN ('Good','Bad','Uncertain')),
    unit                TEXT        NOT NULL,
    source              TEXT        NOT NULL DEFAULT 'MQTT_SPARKPLUG',
    is_simulated        BOOLEAN     NOT NULL DEFAULT TRUE
);

-- Convert to TimescaleDB hypertable partitioned by time
SELECT create_hypertable('telemetry', 'timestamp', if_not_exists => TRUE);

-- Composite index for the most common query pattern
CREATE INDEX IF NOT EXISTS telemetry_asset_tag_time
    ON telemetry (asset_id, tag_name, timestamp DESC);

-- ---------------------------------------------------------------------------
-- tag_health: inferred freshness status per (asset_id, tag_name)
-- Updated by ingestion service on every received message.
-- Checked by freshness_monitor background task to mark tags STALE.
-- This is separate from opc_quality_code — a tag can be GOOD+STALE.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tag_health (
    asset_id                    TEXT        NOT NULL,
    tag_name                    TEXT        NOT NULL,
    last_update                 TIMESTAMPTZ NOT NULL,
    freshness_status            TEXT        NOT NULL DEFAULT 'MISSING'
                                    CHECK (freshness_status IN ('FRESH','STALE','MISSING')),
    staleness_threshold_seconds INTEGER     NOT NULL DEFAULT 10,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asset_id, tag_name)
);

-- ---------------------------------------------------------------------------
-- alarms: triggered threshold events
-- Alarm messages describe observable symptoms only — never fault labels.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alarms (
    alarm_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        TEXT        NOT NULL,
    alarm_type      TEXT        NOT NULL,
    severity        TEXT        NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    message         TEXT        NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    raw_value       DOUBLE PRECISION,
    threshold       DOUBLE PRECISION,
    is_simulated    BOOLEAN     NOT NULL DEFAULT TRUE
);
