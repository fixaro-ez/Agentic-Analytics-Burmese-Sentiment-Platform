# AGENTS.md

## Prerequisites

- **MongoDB** must be running before any scrape: `docker-compose up -d`
- **`cookies.json`** (gitignored) must exist at the **repo root** for Facebook scraping
- **`.env`** at repo root with Supabase PostgreSQL credentials (see `.env.example` in `backend/`)
- **`backend/.env`** with Supabase keys, PG credentials, Google API key (see `backend/.env.example`)
- Python venv (`.venv`) at repo root; backend has its own `requirements.txt`
- Node.js 20+ for the frontend (`frontend/package.json`)
- Windows-only deployment (Task Scheduler, not cron)

## Commands

All Python commands run from the **repo root** with `PYTHONPATH=src`.

### Data Pipeline (Python)

```bash
# Start MongoDB
docker-compose up -d

# Stage 1: Scrape (Facebook)
PYTHONPATH=src python -m burmese_absa --url https://www.facebook.com/<Page> --entity "<Name>" --max-posts 10 --headless

# Stage 1: Scrape (Foodpanda)
PYTHONPATH=src python -m burmese_absa --source foodpanda --url "<shop_url>" --entity "<Name>" --headless

# Stage 2: Clean raw text for ABSA models
PYTHONPATH=src python -m burmese_absa.clean_feedbacks                           # Clean unprocessed docs only
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --reprocess               # Drop and re-clean all
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --status                  # Show cleaning stats

# Stage 3: ABSA inference pipeline
PYTHONPATH=src python -m nlp.run_absa_pipeline                                  # Both pipelines
PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline feedbacks             # Reviews only (Stage 1+2)
PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline contents              # Posts only (Stage 1)
PYTHONPATH=src python -m nlp.run_absa_pipeline --device cuda --batch-size 64    # GPU acceleration
PYTHONPATH=src python -m nlp.run_absa_pipeline --status                         # Show pipeline status

# Stage 4: Export to Supabase PostgreSQL
PYTHONPATH=src python -m nlp.export_to_postgres                                 # Export ABSA results
PYTHONPATH=src python -m nlp.export_to_postgres --dry-run                       # Preview
PYTHONPATH=src python -m nlp.export_to_postgres --status                        # Row counts

# Utility commands
PYTHONPATH=src python -m burmese_absa --status                                  # Check tracking status
PYTHONPATH=src python -m burmese_absa.ingest_to_mongo <file.json>              # JSON backfill (non-Facebook only)
```

### Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev          # Dev server on http://localhost:3000
npm run build        # Production build
npm run lint         # ESLint
```

### Tests

```bash
# Scraper tests (unittest, from repo root)
PYTHONPATH=src python -m unittest tests.test_facebook_posts
PYTHONPATH=src python -m unittest tests.test_foodpanda

# Backend tests (pytest, from backend/)
cd backend
pip install -r requirements.txt
python -m pytest tests/

# Frontend tests (node --test, from frontend/)
cd frontend
npm run test:mining
npm run test:analytics
npm run test:scraping
```

### Database Migrations

Apply in Supabase SQL Editor in order:

```text
init_db.sql                                              # Base star schema + scrape management
migrations/20260731_brand_benchmark_impact.sql           # Historical brands/benchmark schema
migrations/20260801_etl_health_scrape_management.sql     # ETL runs, scrape entities/runs/schedules
migrations/20260801_pipeline_default_and_integrity.sql   # Pipeline defaults and integrity
migrations/20260801_scrape_schedule_fk_index.sql         # Schedule FK index
migrations/20260802_security_and_integrity_hardening.sql # RLS, grants, constraints, secure views
migrations/20260802_review_level_sentiment_views.sql     # Distinct-review overview and trend metrics
migrations/20260802_remove_social_post_classifications.sql # Remove retired impact schema
migrations/20260804_five_aspect_model_cutover.sql         # Retrained five-aspect taxonomy cutover
views.sql                                                # Analytics views
```

## Project Layout

```
Selenium/
├── src/
│   ├── burmese_absa/                # Data ingestion package
│   │   ├── __init__.py
│   │   ├── __main__.py              # CLI entry: python -m burmese_absa
│   │   ├── scraping/                # Unified scraper (split into submodules)
│   │   │   ├── __init__.py          # Re-exports all public symbols
│   │   │   ├── __main__.py          # python -m burmese_absa.scraping → CLI
│   │   │   ├── _config.py           # MongoDB URI, REACTION_KEYS, FOODPANDA_* constants
│   │   │   ├── _common.py           # Timestamp parsers, text normalizers
│   │   │   ├── storage.py           # In-memory session_data + JSON export
│   │   │   ├── lifecycle.py         # 30-day MongoDB lifecycle, get_db, indexes
│   │   │   ├── facebook.py          # Async Facebook post + reaction scraping
│   │   │   ├── foodpanda.py         # Sync Foodpanda review scraping
│   │   │   └── cli.py               # argparse CLI (interactive + non-interactive)
│   │   ├── clean_feedbacks.py       # 5-stage Burmese text cleaning
│   │   └── ingest_to_mongo.py       # JSON backfill (non-Facebook only)
│   └── nlp/                         # NLP pipeline package
│       ├── __init__.py
│       ├── run_absa_pipeline.py     # 2-stage ABSA inference
│       └── export_to_postgres.py    # MongoDB → Supabase ETL
├── backend/                         # FastAPI backend
│   ├── app/
│   │   ├── main.py                  # FastAPI app, lifespan, CORS, router mounts
│   │   ├── auth.py                  # Supabase JWT bearer auth (AuthUser, get_current_user)
│   │   ├── config.py                # pydantic-settings (SUPABASE_*, PG_*, GOOGLE_*, MONGO_URI)
│   │   ├── database.py              # asyncpg pool + Supabase client singletons
│   │   ├── models/                  # Pydantic schemas (analytics, benchmark, brands, chat, entities, etl, mining, scraping)
│   │   ├── routers/                 # Route handlers (analytics, brands, chat, entities, etl, mining, scraping)
│   │   └── services/                # Business logic (analytics, benchmark, brands, chat, entities, etl, mining, scraping)
│   ├── tests/                       # Backend pytest tests
│   │   ├── test_analytics.py
│   │   ├── test_benchmark.py
│   │   ├── test_chat.py
│   │   ├── test_etl_health.py
│   │   ├── test_health.py
│   │   ├── test_mining.py
│   │   ├── test_pipeline_freshness.py
│   │   └── test_scraping.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/                        # Next.js 16 frontend (React 19)
│   ├── src/
│   │   ├── app/
│   │   │   ├── (app)/               # Authenticated routes
│   │   │   │   ├── dashboard/       # Main analytics dashboard
│   │   │   │   ├── entities/        # Entity list + [id] detail
│   │   │   │   ├── analytics/       # Overview + Benchmark tabs
│   │   │   │   ├── chat/            # Chat with Data (AI workspace)
│   │   │   │   ├── mining/          # Association rules + entity clusters
│   │   │   │   └── scraping/        # Scrape control center
│   │   │   ├── api/                 # Next.js API routes (chat-sql proxy)
│   │   │   ├── login/               # Supabase auth (sign in/up/forgot)
│   │   │   ├── layout.tsx           # Root layout
│   │   │   ├── globals.css          # Design tokens, dark mode surfaces
│   │   │   └── page.tsx             # Redirect → /dashboard
│   │   ├── components/
│   │   │   ├── analytics/           # Brand mapping and benchmark panels
│   │   │   ├── charts/              # Recharts: sentiment trends, aspect bars, engagement, radar, donuts
│   │   │   ├── chat/                # AI chat workspace (streaming, inline viz, pinning)
│   │   │   ├── dashboard/           # KPI strip, aspect radar, top drivers, social engagement
│   │   │   ├── etl/                 # ETL health dialog
│   │   │   ├── layout/              # Sidebar, header, filter bar, filter sync
│   │   │   ├── mining/              # Association rules + entity clusters panels
│   │   │   ├── scraping/            # Scrape manager drawer
│   │   │   ├── ui/                  # shadcn primitives (button, card, dialog, tabs, etc.)
│   │   │   ├── providers.tsx        # TanStack Query + next-themes + toast providers
│   │   │   ├── data-error.tsx       # Reusable error state
│   │   │   └── error-boundary.tsx   # React error boundary
│   │   ├── hooks/                   # use-api.ts, use-analytics.ts
│   │   └── lib/                     # api.ts, types.ts, myanmar.ts, stores/, supabase/, utils
│   ├── AGENTS.md                    # Frontend-specific agent instructions
│   ├── package.json
│   └── .env.local.example
├── models/                          # Local ML model weights (gitignored)
│   ├── stage1_xlm_roberta_base/     # Five-aspect detection
│   └── stage2_xlm_roberta_base/     # Sentiment classification
├── tests/                           # Scraper tests (unittest)
│   ├── __init__.py
│   ├── test_facebook_posts.py
│   └── test_foodpanda.py
├── migrations/                      # Supabase SQL migrations
│   ├── 20260731_brand_benchmark_impact.sql
│   ├── 20260801_etl_health_scrape_management.sql
│   ├── 20260801_pipeline_default_and_integrity.sql
│   ├── 20260801_scrape_schedule_fk_index.sql
│   ├── 20260802_remove_social_post_classifications.sql
│   └── 20260804_five_aspect_model_cutover.sql
├── docs/
│   ├── CAPSTONE_PROJECT.md
│   ├── Project_Database_Design.md
│   ├── BI-NLP-Dashboard-UIUX-Architecture-v3.md
│   ├── etl-scrape-management.md
│   ├── implementation_plan.md
│   ├── TASK_ASSIGNMENTS.md
├── init_db.sql                      # Base DDL (star schema + scrape management)
├── views.sql                        # Analytics views (power API endpoints)
├── docker-compose.yaml              # MongoDB container
├── .env                             # Root env (PG credentials for export script)
├── cookies.json                     # Facebook auth cookies (gitignored)
├── opencode.json                    # OpenCode configuration
└── AGENTS.md                        # This file
```

## Architecture

### Data Pipeline (Python CLI)

- **Single CLI entry point**: `python -m burmese_absa` invokes `burmese_absa.scraping.cli.main()`.
- **`burmese_absa.scraping`** is the unified scraper. It is a package split into focused submodules, but every public symbol is re-exported from `burmese_absa.scraping` for backward compatibility.
- **Facebook uses `async_playwright`**, Foodpanda/blog use `sync_playwright`. Both write to MongoDB.
- **`ingest_to_mongo.py`** is only for non-Facebook sources and backfills.
- **MongoDB** is the data lake. Database: `feedback_analytics`, collections: `contents`, `feedbacks`, `cleaned_contents`, `cleaned_feedbacks`, `absa_processed_contents`, `absa_processed_feedbacks`.
- **`clean_feedbacks.py`** is the 5-stage Burmese-aware text cleaning pipeline. Writes to separate cleaned collections. Original data is never modified.
- **`run_absa_pipeline.py`** runs 2-stage ABSA inference (aspect detection + sentiment classification) on cleaned text.
- **`export_to_postgres.py`** exports ABSA results from MongoDB to the Supabase PostgreSQL star schema.

### Backend (FastAPI)

- **FastAPI app** at `backend/app/main.py` with lifespan-managed scheduler and asyncpg pool.
- **Supabase JWT auth** via `auth.py` — every endpoint requires a valid bearer token.
- **7 routers** mounted under `/api/`: entities, brands, analytics, etl, chat, mining, scraping.
- **Services layer** contains all business logic; routers are thin.
- **Scheduler** runs inside the FastAPI lifespan, checks `scrape_schedules` every 60 seconds, triggers due scrapes.
- **Database access**: asyncpg pool for PostgreSQL reads/writes, Supabase client for auth, pymongo for MongoDB.

### Frontend (Next.js 16 + React 19)

- **Dark-first theme** with semantic design tokens (sentiment, alert, entity, pipeline colors as CSS variables).
- **Supabase Auth** for login/signup, JWT auto-attached to API calls.
- **Zustand** global filter store (entity, days, aspect) synced to URL params; comparison controls remain local to the analysis that uses them.
- **TanStack Query** for server state with `useApi()` wrapper supporting polling.
- **shadcn/ui** primitives (new-york style) in `src/components/ui/`.
- **Recharts** for all chart visualizations.
- **Noto Sans Myanmar** font for Burmese text, Geist for English/Burglish.

### PostgreSQL Star Schema (Supabase)

| Table | Description |
|---|---|
| `dim_entities` | Dimension: shops and pages (entity_name, platform, metadata) |
| `dim_brands` | Brand-to-Facebook-page mapping |
| `bridge_brand_foodpanda_shops` | Brand-to-Foodpanda-shop many-to-many |
| `fact_social_posts` | Facebook posts with reactions + ABSA-promoted aspects |
| `fact_review_absa_results` | Review ABSA results in long format (one row per aspect-sentiment pair) |
| `etl_runs` | Pipeline audit log (backward-compatible canonical source) |
| `scrape_entities` | Saved scrape targets (owner-scoped, RLS) |
| `scrape_runs` | Live scrape progress (references etl_runs, RLS) |
| `scrape_schedules` | Cron schedules with IANA timezone (RLS) |

Views in `views.sql`: `v_entity_sentiment_overview`, `v_aspect_breakdown`, and others power analytics API endpoints.

## Testing Quirks

- `tests/test_foodpanda.py` **mocks all imports** (`playwright`, `pymongo`) at the top of the file. Tests must work with these mocks.
- Scraper tests use `unittest` — no pytest config, no test runner script.
- Facebook tests import pure functions from `burmese_absa.scraping` — no browser or DB needed.
- Foodpanda tests use `importlib.import_module('burmese_absa.scraping')` and `importlib.import_module('burmese_absa.ingest_to_mongo')` so the mocks apply.
- Backend tests use **pytest** and are in `backend/tests/`.
- Frontend tests use **node --test** with `--experimental-strip-types` (see `package.json` scripts).
- Frontend verification: `npm run lint` and `npm run build`.

## Key Conventions

- Facebook reaction counts: unknown categories are `None`, never `0`. Incomplete breakdowns never produce false-zero ratios.
- Reaction keys: `("like", "love", "care", "haha", "wow", "sad", "angry")`
- Burmese text, digits, and month names are first-class — encoding is forced to UTF-8 at startup.
- `engagement_history` is capped at 100 snapshots per post (`MAX_ENGAGEMENT_HISTORY`).
- `facebook_data.json` is debug output only — never ingest it via `ingest_to_mongo`.
- **ABSA aspects** (5): `product_quality`, `fulfillment_and_speed`, `price_and_value`, `staff_and_service`, `variety_and_availability`.
- **Sentiment labels** (3): `Positive`, `Negative`, `Neutral`.
- Dedup key: `_id = fb_post_<sha256(normalized_page_url + platform_content_id)>`.
- 30-day lifecycle: posts within 30 days get engagement-only updates; expired posts are marked `lifecycle_status: "final"`.
- Derived metrics must always be recalculated immediately before MongoDB writes.
- Frontend: never use generic `green-500`/`red-500` for sentiment; always use semantic tokens (`text-sentiment-positive`, etc.).
- Frontend: dark is the default theme; `<html>` has `suppressHydrationWarning`.
- All scrape management tables have RLS enabled and are owner-scoped to `auth.uid()`.
