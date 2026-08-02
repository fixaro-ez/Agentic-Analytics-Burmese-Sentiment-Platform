-- New scrapes process and publish data by default.
-- Existing saved-target choices are preserved; only future row defaults change.

ALTER TABLE public.scrape_entities
    ALTER COLUMN auto_pipeline SET DEFAULT TRUE;

ALTER TABLE public.scrape_runs
    ALTER COLUMN run_full_pipeline SET DEFAULT TRUE;
