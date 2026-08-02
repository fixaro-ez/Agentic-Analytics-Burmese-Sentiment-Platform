-- ETL health remains a read-only projection over etl_runs and warehouse facts.
-- These additive tables persist saved scrape targets, live run metadata, and
-- schedules while etl_runs remains the backward-compatible audit source.

CREATE TABLE IF NOT EXISTS etl_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds FLOAT,
    stats JSONB,
    error TEXT,
    triggered_by UUID
);

CREATE TABLE IF NOT EXISTS scrape_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dim_entity_id INT REFERENCES dim_entities(entity_id) ON DELETE SET NULL,
    source VARCHAR(20) NOT NULL CHECK (source IN ('facebook', 'foodpanda')),
    source_url TEXT NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    max_posts INT NOT NULL DEFAULT 10 CHECK (max_posts BETWEEN 1 AND 200),
    headless BOOLEAN NOT NULL DEFAULT TRUE,
    auto_pipeline BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_scraped_at TIMESTAMPTZ,
    last_scrape_status VARCHAR(20),
    last_scrape_error TEXT,
    UNIQUE (created_by, source_url)
);

CREATE INDEX IF NOT EXISTS scrape_entities_created_by_idx
    ON scrape_entities (created_by, updated_at DESC);
CREATE INDEX IF NOT EXISTS scrape_entities_dim_entity_idx
    ON scrape_entities (dim_entity_id);

CREATE TABLE IF NOT EXISTS scrape_runs (
    run_id UUID PRIMARY KEY REFERENCES etl_runs(run_id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entity_id UUID REFERENCES scrape_entities(id) ON DELETE SET NULL,
    source VARCHAR(20) NOT NULL CHECK (source IN ('facebook', 'foodpanda')),
    source_url TEXT NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    phase VARCHAR(30) NOT NULL DEFAULT 'queued',
    progress_percent INT NOT NULL DEFAULT 0
        CHECK (progress_percent BETWEEN 0 AND 100),
    cancellation_requested BOOLEAN NOT NULL DEFAULT FALSE,
    run_full_pipeline BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_kind VARCHAR(20) NOT NULL DEFAULT 'manual'
        CHECK (trigger_kind IN ('manual', 'saved_entity', 'schedule')),
    diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS scrape_runs_created_by_idx
    ON scrape_runs (created_by, created_at DESC);
CREATE INDEX IF NOT EXISTS scrape_runs_entity_idx
    ON scrape_runs (entity_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS scrape_runs_one_active_target_idx
    ON scrape_runs (created_by, source, source_url)
    WHERE status IN ('queued', 'running', 'cancelling');

CREATE TABLE IF NOT EXISTS scrape_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES scrape_entities(id) ON DELETE CASCADE,
    cron_expression VARCHAR(100) NOT NULL,
    timezone VARCHAR(100) NOT NULL DEFAULT 'Asia/Yangon',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_run TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    UNIQUE (created_by, entity_id)
);

CREATE INDEX IF NOT EXISTS scrape_schedules_due_idx
    ON scrape_schedules (next_run)
    WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS scrape_schedules_created_by_idx
    ON scrape_schedules (created_by);
CREATE INDEX IF NOT EXISTS scrape_schedules_entity_id_idx
    ON scrape_schedules (entity_id);

ALTER TABLE scrape_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_schedules ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS scrape_entities_owner_all ON scrape_entities;
CREATE POLICY scrape_entities_owner_all ON scrape_entities
    FOR ALL TO authenticated
    USING ((SELECT auth.uid()) = created_by)
    WITH CHECK ((SELECT auth.uid()) = created_by);

DROP POLICY IF EXISTS scrape_runs_owner_select ON scrape_runs;
CREATE POLICY scrape_runs_owner_select ON scrape_runs
    FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = created_by);

DROP POLICY IF EXISTS scrape_schedules_owner_all ON scrape_schedules;
CREATE POLICY scrape_schedules_owner_all ON scrape_schedules
    FOR ALL TO authenticated
    USING ((SELECT auth.uid()) = created_by)
    WITH CHECK ((SELECT auth.uid()) = created_by);
