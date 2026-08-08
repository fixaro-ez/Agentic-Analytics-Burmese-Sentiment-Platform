# Project Database Design (Star Schema)

*PostgreSQL · Aspect-Based Sentiment Analysis (ABSA) Project*

This document outlines the comprehensive PostgreSQL database design for the Aspect-Based Sentiment Analysis (ABSA) project, utilizing a Star Schema architecture. This design accommodates Foodpanda reviews (with ABSA results), Facebook engagement metrics, brand mapping, campaign classification, ETL audit, and scrape management.

## 1. Overview

The architecture consists of dimension tables, fact tables, ETL audit tables, and scrape management tables. The dimension table stores entity information (shops/pages), and the fact tables store transactional/event data (reviews and social posts). They are linked via a one-to-many relationship. Brand mapping and scrape management tables support competitive analysis and automated scheduling.

## 2. Dimension Table: `dim_entities`

This table acts as the central hub, storing metadata for both Foodpanda shops and Facebook pages. It uses a JSONB column to flexibly store platform-specific attributes without requiring sparse columns.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `entity_id` | SERIAL | PRIMARY KEY | Unique auto-generated identifier for the entity. |
| `entity_name` | VARCHAR(255) | NOT NULL | Name of the entity (e.g., "Lotteria Myanmar", "Reviews OMUK (CW)"). |
| `platform` | VARCHAR(50) | NOT NULL | Platform of the entity (e.g., 'facebook', 'foodpanda'). |
| `platform_metadata` | JSONB | — | Flexible storage for platform-specific data.<br>Foodpanda Ex: `{"source_shop_id": "shop_d00190c6cd63aa35"}`<br>Facebook Ex: `{"page_url": "https://www.facebook.com/LotteriaMyanmar"}` |

**SQL Creation Script**

```sql
CREATE TABLE dim_entities (
    entity_id SERIAL PRIMARY KEY,
    entity_name VARCHAR(255) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    platform_metadata JSONB,
    UNIQUE (entity_name, platform)
);
```

## 3. Fact Table 1: `fact_social_posts`

This table stores engagement metrics scraped from Facebook posts. It links back to the dim_entities table to associate the post with a specific Facebook page.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `post_id` | VARCHAR(100) | PRIMARY KEY | Unique ID from the source (e.g., "fb_post_cd17d2..."). |
| `entity_id` | INT | REFERENCES dim_entities(entity_id) | Foreign key linking to the page in dim_entities. |
| `post_timestamp` | TIMESTAMP | — | Time the post was published. |
| `post_text` | TEXT | — | The full text of the Facebook post. |
| `promoted_aspects` | TEXT[] | — | Array of detected aspects from ABSA Stage 1. |
| `aspect_confidence` | JSONB | — | Confidence scores per detected aspect. |
| `total_reactions` | INT | — | Total number of reactions. |
| `like_count` | INT | — | Number of 'Like' reactions. |
| `love_count` | INT | — | Number of 'Love' reactions. |
| `haha_count` | INT | — | Number of 'Haha' reactions. |
| `sad_count` | INT | — | Number of 'Sad' reactions. |
| `angry_count` | INT | — | Number of 'Angry' reactions. |
| `care_count` | INT | — | Number of 'Care' reactions. |
| `wow_count` | INT | — | Number of 'Wow' reactions. |
| `shares_count` | INT | — | Number of shares. |
| `comments_count` | INT | — | Number of comments. |
| `positivity_ratio` | DECIMAL(5,4) | — | Calculated metric (e.g., 0.1007). |
| `negativity_ratio` | DECIMAL(5,4) | — | Calculated metric. |

**SQL Creation Script**

```sql
CREATE TABLE fact_social_posts (
    post_id VARCHAR(100) PRIMARY KEY,
    entity_id INT REFERENCES dim_entities(entity_id),
    post_timestamp TIMESTAMP,
    post_text TEXT,
    promoted_aspects TEXT[],
    aspect_confidence JSONB,
    total_reactions INT,
    like_count INT,
    love_count INT,
    haha_count INT,
    sad_count INT,
    angry_count INT,
    care_count INT,
    wow_count INT,
    shares_count INT,
    comments_count INT,
    positivity_ratio DECIMAL(5,4),
    negativity_ratio DECIMAL(5,4)
);
```

## 4. Fact Table 2: `fact_review_absa_results`

This table stores the final output from the two-stage NLP pipeline. It uses a "Long Format" design, meaning a single review may generate multiple rows if multiple aspects are detected.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `result_id` | SERIAL | PRIMARY KEY | Unique auto-generated ID for the specific aspect-sentiment result. |
| `feedback_id` | VARCHAR(100) | NOT NULL | ID of the original review (e.g., "fp_rev_274e43b4..."). |
| `entity_id` | INT | REFERENCES dim_entities(entity_id) | Foreign key linking to the shop in dim_entities. |
| `feedback_timestamp` | TIMESTAMP | — | Time the review was posted. |
| `raw_text` | TEXT | — | The original, cleaned review text. |
| `aspect_category` | VARCHAR(100) | — | The aspect detected by Stage 1 (e.g., 'product_quality'). If no aspect is detected, this will be 'no_aspect'. |
| `sentiment_label` | VARCHAR(20) | — | The sentiment output by Stage 2 ('Positive', 'Negative', 'Neutral'). |
| `confidence_score` | DECIMAL(5,4) | — | The confidence score from the Stage 2 model (e.g., 0.9850). |

**SQL Creation Script**

```sql
CREATE TABLE fact_review_absa_results (
    result_id SERIAL PRIMARY KEY,
    feedback_id VARCHAR(100) NOT NULL,
    entity_id INT REFERENCES dim_entities(entity_id),
    feedback_timestamp TIMESTAMP,
    raw_text TEXT,
    aspect_category VARCHAR(100),
    sentiment_label VARCHAR(20),
    confidence_score DECIMAL(5,4)
);
```

## 5. Brand Mapping: `dim_brands`

Maps a brand to its Facebook page entity. Each brand has exactly one Facebook page.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `brand_id` | SERIAL | PRIMARY KEY | Unique brand identifier. |
| `brand_name` | VARCHAR(255) | NOT NULL, UNIQUE | Human-readable brand name. |
| `facebook_entity_id` | INT | NOT NULL, UNIQUE, FK → dim_entities | The Facebook page representing this brand. |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update timestamp. |

## 6. Bridge Table: `bridge_brand_foodpanda_shops`

Many-to-many relationship between brands and their Foodpanda shop entities.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `brand_id` | INT | FK → dim_brands, PK | Brand reference. |
| `entity_id` | INT | UNIQUE, FK → dim_entities, PK | Foodpanda shop entity. |

## 7. ETL Audit: `etl_runs`

Canonical pipeline audit table. Records every ETL run with timing, status, stats, and errors.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `run_id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique run identifier. |
| `run_type` | VARCHAR(30) | NOT NULL | Type of ETL run (e.g., 'clean', 'absa', 'export', 'full'). |
| `status` | VARCHAR(20) | DEFAULT 'running' | Current status (running, completed, failed). |
| `started_at` | TIMESTAMPTZ | DEFAULT NOW() | Start time. |
| `completed_at` | TIMESTAMPTZ | — | Completion time. |
| `duration_seconds` | FLOAT | — | Wall-clock duration. |
| `stats` | JSONB | — | Run statistics (row counts, deltas). |
| `error` | TEXT | — | Error message if failed. |
| `triggered_by` | UUID | — | Authenticated user who triggered the run. |

## 8. Scrape Management: `scrape_entities`

Saved scrape targets. Owner-scoped via RLS to `auth.uid()`.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique target identifier. |
| `created_by` | UUID | FK → auth.users, NOT NULL | Owner. |
| `dim_entity_id` | INT | FK → dim_entities (ON DELETE SET NULL) | Linked warehouse entity (optional). |
| `source` | VARCHAR(20) | CHECK IN ('facebook', 'foodpanda') | Source platform. |
| `source_url` | TEXT | NOT NULL | URL to scrape. |
| `display_name` | VARCHAR(200) | NOT NULL | Human-readable name. |
| `max_posts` | INT | DEFAULT 10, CHECK 1–200 | Max posts per scrape (Facebook only). |
| `headless` | BOOLEAN | DEFAULT TRUE | Run browser headless. |
| `auto_pipeline` | BOOLEAN | DEFAULT TRUE | Run full ETL pipeline after scrape. |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update timestamp. |
| `last_scraped_at` | TIMESTAMPTZ | — | Last successful scrape time. |
| `last_scrape_status` | VARCHAR(20) | — | Last scrape outcome. |
| `last_scrape_error` | TEXT | — | Last scrape error message. |

UNIQUE constraint: `(created_by, source_url)` prevents duplicate targets per user.

## 9. Scrape Runs: `scrape_runs`

Live scrape progress. `run_id` references `etl_runs` so scrape runs and ETL audit share one identity.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `run_id` | UUID | PRIMARY KEY, FK → etl_runs | Shared audit identity. |
| `created_by` | UUID | FK → auth.users, NOT NULL | Owner. |
| `entity_id` | UUID | FK → scrape_entities (ON DELETE SET NULL) | Linked saved target. |
| `source` | VARCHAR(20) | CHECK IN ('facebook', 'foodpanda') | Source platform. |
| `source_url` | TEXT | NOT NULL | Scraped URL. |
| `display_name` | VARCHAR(200) | NOT NULL | Human-readable name. |
| `status` | VARCHAR(20) | DEFAULT 'queued' | Run status. |
| `phase` | VARCHAR(30) | DEFAULT 'queued' | Current pipeline phase. |
| `progress_percent` | INT | DEFAULT 0, CHECK 0–100 | Completion percentage. |
| `cancellation_requested` | BOOLEAN | DEFAULT FALSE | Cooperative cancel flag. |
| `run_full_pipeline` | BOOLEAN | DEFAULT TRUE | Whether to run full ETL. |
| `trigger_kind` | VARCHAR(20) | CHECK IN ('manual', 'saved_entity', 'schedule') | How the run was triggered. |
| `diagnostics` | JSONB | DEFAULT '{}' | Run diagnostics and counts. |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Queued timestamp. |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update. |

Partial unique index enforces one active run per owner/source/URL:
```sql
CREATE UNIQUE INDEX scrape_runs_one_active_target_idx
    ON scrape_runs (created_by, source, source_url)
    WHERE status IN ('queued', 'running', 'cancelling');
```

## 10. Scrape Schedules: `scrape_schedules`

Cron-based recurring scrape schedules with IANA timezone support. Owner-scoped via RLS.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique schedule identifier. |
| `created_by` | UUID | FK → auth.users, NOT NULL | Owner. |
| `entity_id` | UUID | FK → scrape_entities (ON DELETE CASCADE), NOT NULL | Target to scrape. |
| `cron_expression` | VARCHAR(100) | NOT NULL | 5-field cron expression. |
| `timezone` | VARCHAR(100) | DEFAULT 'Asia/Yangon' | IANA timezone for cron evaluation. |
| `active` | BOOLEAN | DEFAULT TRUE | Whether the schedule is enabled. |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update timestamp. |
| `next_run` | TIMESTAMPTZ | — | Next scheduled execution time. |
| `last_run_at` | TIMESTAMPTZ | — | Last execution time. |

UNIQUE constraint: `(created_by, entity_id)` — one schedule per user per target.

## 11. Indexes

```sql
-- Analytics access paths
CREATE INDEX fact_social_posts_entity_timestamp_idx
    ON fact_social_posts (entity_id, post_timestamp);
CREATE INDEX fact_review_absa_entity_timestamp_idx
    ON fact_review_absa_results (entity_id, feedback_timestamp);
CREATE INDEX fact_review_absa_feedback_idx
    ON fact_review_absa_results (feedback_id);

-- Brand mapping
CREATE INDEX brand_foodpanda_brand_idx
    ON bridge_brand_foodpanda_shops (brand_id);
-- Scrape management
CREATE INDEX scrape_entities_created_by_idx
    ON scrape_entities (created_by, updated_at DESC);
CREATE INDEX scrape_entities_dim_entity_idx
    ON scrape_entities (dim_entity_id);
CREATE INDEX scrape_runs_created_by_idx
    ON scrape_runs (created_by, created_at DESC);
CREATE INDEX scrape_runs_entity_idx
    ON scrape_runs (entity_id, created_at DESC);
CREATE INDEX scrape_schedules_due_idx
    ON scrape_schedules (next_run) WHERE active = TRUE;
CREATE INDEX scrape_schedules_created_by_idx
    ON scrape_schedules (created_by);
CREATE INDEX scrape_schedules_entity_id_idx
    ON scrape_schedules (entity_id);
```

## 12. Row Level Security

All scrape management tables have RLS enabled. Saved targets, schedules, and run reads are owner-scoped to `auth.uid()`. The FastAPI service also filters every resource by the authenticated user to prevent IDOR access.

```sql
ALTER TABLE scrape_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_schedules ENABLE ROW LEVEL SECURITY;

CREATE POLICY scrape_entities_owner_all ON scrape_entities
    FOR ALL TO authenticated
    USING ((SELECT auth.uid()) = created_by)
    WITH CHECK ((SELECT auth.uid()) = created_by);

CREATE POLICY scrape_runs_owner_select ON scrape_runs
    FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = created_by);

CREATE POLICY scrape_schedules_owner_all ON scrape_schedules
    FOR ALL TO authenticated
    USING ((SELECT auth.uid()) = created_by)
    WITH CHECK ((SELECT auth.uid()) = created_by);
```

## 14. Analytics Views

Views in `views.sql` power the backend analytics API endpoints:

| View | Used By | Description |
|---|---|---|
| `v_entity_sentiment_overview` | `GET /api/analytics/entities` | Per-entity sentiment counts and ratios from `fact_review_absa_results` |
| `v_aspect_breakdown` | `GET /api/analytics/aspects` | Aspect × sentiment breakdown (excludes `no_aspect`) |
| `v_sentiment_daily_trends` | `GET /api/analytics/trends` | Daily sentiment time-series per entity |
| `v_facebook_engagement` | `GET /api/analytics/engagement` | Facebook engagement aggregates per entity |
| `v_entity_aspect_summary` | Data mining | Entity × aspect × sentiment summary for clustering |

## 15. Migration Order

Apply in Supabase SQL Editor in this order:

```text
init_db.sql                                              # Base star schema + scrape management + RLS
migrations/20260731_brand_benchmark_impact.sql           # dim_brands, bridge, classifications
migrations/20260801_etl_health_scrape_management.sql     # etl_runs, scrape_entities, scrape_runs, scrape_schedules
migrations/20260801_pipeline_default_and_integrity.sql   # auto_pipeline and run_full_pipeline defaults
migrations/20260801_scrape_schedule_fk_index.sql         # scrape_schedules entity_id index
migrations/20260802_remove_social_post_classifications.sql # remove retired impact schema
migrations/20260804_five_aspect_model_cutover.sql         # retrained five-aspect taxonomy
views.sql                                                # Analytics views
```
