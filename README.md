# Burmese ABSA Analytics Platform

End-to-end data pipeline and Agentic AI platform for decoding Burmese sentiment in the Myanmar market. Extracts raw customer feedback from Facebook and Foodpanda, applies a custom two-stage Aspect-Based Sentiment Analysis (ABSA) model, stores results in a PostgreSQL star schema (Supabase), and surfaces insights via a BI dashboard with "Chat with Data".

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  SCRAPE              CLEAN              ABSA                EXPORT                 │
│                                                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐    ┌─────────┐           │
│  │Facebook  │    │clean_        │    │run_absa_       │    │export_  │           │
│  │Foodpanda │───►│feedbacks.py  │───►│pipeline.py     │───►│to_      │           │
│  │Blog      │    │(5-stage)     │    │(2-stage ABSA)  │    │postgres │           │
│  └──────────┘    └──────────────┘    └────────────────┘    └────┬────┘           │
│       │               │                     │                    │                 │
│       ▼               ▼                     ▼                    ▼                 │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │                         MongoDB (Data Lake)                                 │   │
│  │  contents → cleaned_contents → absa_processed_contents                      │   │
│  │  feedbacks → cleaned_feedbacks → absa_processed_feedbacks                   │   │
│  └────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │                  Supabase (PostgreSQL Star Schema)                           │   │
│  │  dim_entities │ dim_brands │ fact_social_posts │ fact_review_absa_results   │   │
│  │  etl_runs │ scrape_entities │ scrape_runs │ scrape_schedules                │   │
│  └────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                          │
│                                        ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │                       FastAPI Backend (7 routers)                            │   │
│  │  entities │ brands │ analytics │ etl │ chat │ mining │ scraping             │   │
│  └────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                          │
│                                        ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │                    Next.js 16 Frontend (React 19)                            │   │
│  │  Dashboard │ Entities │ Analytics │ Chat │ Mining │ Scraping                │   │
│  └────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Pipeline Stages

| Stage | Module | Input | Output |
|---|---|---|---|
| 1. Scrape | `burmese_absa.scraping` | Facebook/Foodpanda/Blog URLs | `contents` + `feedbacks` (MongoDB) |
| 2. Clean | `burmese_absa.clean_feedbacks` | Raw text from MongoDB | `cleaned_contents` + `cleaned_feedbacks` (MongoDB) |
| 3. ABSA | `nlp.run_absa_pipeline` | Cleaned text | `absa_processed_contents` + `absa_processed_feedbacks` (MongoDB) |
| 4. Export | `nlp.export_to_postgres` | ABSA results | Supabase PostgreSQL star schema |

## Tech Stack

| Layer | Technology |
|---|---|
| Scraping | Python, Playwright (async for Facebook, sync for Foodpanda) |
| Data Lake | MongoDB (Docker) |
| Text Cleaning | Custom 5-stage Burmese-aware pipeline (Zawgyi/Unicode/Burglish) |
| NLP Models | PyTorch, XLM-RoBERTa (HuggingFace) |
| Data Warehouse | Supabase (PostgreSQL Star Schema) |
| Backend | FastAPI, asyncpg, Supabase JWT auth, Google Gemini |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, Recharts, Zustand, TanStack Query |
| Scheduling | Supabase-backed cron schedules + FastAPI local browser worker |

## Project Structure

```
Selenium/
├── src/
│   ├── burmese_absa/                # Data ingestion package
│   │   ├── __init__.py
│   │   ├── __main__.py              # CLI entry: python -m burmese_absa
│   │   ├── scraping/                # Unified scraper (split into submodules)
│   │   │   ├── _config.py           # MongoDB URI, REACTION_KEYS, constants
│   │   │   ├── _common.py           # Timestamp parsers, text normalizers
│   │   │   ├── storage.py           # In-memory session_data + JSON export
│   │   │   ├── lifecycle.py         # 30-day MongoDB lifecycle, indexes
│   │   │   ├── facebook.py          # Async Facebook post + reaction scraping
│   │   │   ├── foodpanda.py         # Sync Foodpanda review scraping
│   │   │   └── cli.py               # argparse CLI (interactive + non-interactive)
│   │   ├── clean_feedbacks.py       # 5-stage Burmese text cleaning
│   │   └── ingest_to_mongo.py       # JSON backfill (non-Facebook only)
│   └── nlp/                         # NLP pipeline package
│       ├── run_absa_pipeline.py     # 2-stage ABSA inference
│       └── export_to_postgres.py    # MongoDB → Supabase ETL
├── backend/                         # FastAPI backend
│   ├── app/
│   │   ├── main.py                  # App entry, lifespan, CORS, router mounts
│   │   ├── auth.py                  # Supabase JWT bearer auth
│   │   ├── config.py                # pydantic-settings configuration
│   │   ├── database.py              # asyncpg pool + Supabase client
│   │   ├── models/                  # Pydantic schemas (8 modules)
│   │   ├── routers/                 # Route handlers (7 routers)
│   │   └── services/                # Business logic (8 service modules)
│   ├── tests/                       # Backend pytest tests (8 test files)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                        # Next.js 16 frontend (React 19)
│   ├── src/
│   │   ├── app/                     # Pages: dashboard, entities, analytics, chat, mining, scraping, login
│   │   ├── components/              # UI: charts, dashboard, analytics, chat, layout, mining, scraping, etl, ui/
│   │   ├── hooks/                   # use-api.ts, use-analytics.ts
│   │   └── lib/                     # api.ts, types.ts, myanmar.ts, stores/, supabase/
│   ├── AGENTS.md                    # Frontend-specific agent instructions
│   └── package.json
├── models/                          # Local ML model weights (gitignored)
│   ├── stage1_xlm_roberta_large/    # Aspect detection
│   └── stage2_xlm_roberta_base/     # Sentiment classification
├── tests/                           # Scraper tests (unittest)
│   ├── test_facebook_posts.py       # Pure function tests (no browser)
│   └── test_foodpanda.py            # Mocked Playwright + pymongo tests
├── migrations/                      # Supabase SQL migrations
│   ├── 20260731_brand_benchmark_impact.sql
│   ├── 20260801_etl_health_scrape_management.sql
│   ├── 20260801_pipeline_default_and_integrity.sql
│   ├── 20260801_scrape_schedule_fk_index.sql
│   └── 20260802_remove_social_post_classifications.sql
├── docs/                            # Project documentation
├── init_db.sql                      # Base DDL (star schema + scrape management)
├── views.sql                        # Analytics views (power API endpoints)
├── docker-compose.yaml              # MongoDB container
├── .env                             # Root env (PG credentials for export script)
├── cookies.json                     # Facebook auth cookies (gitignored)
└── AGENTS.md                        # AI agent coding instructions
```

## Prerequisites

- **Python 3.10+** with a virtual environment (`.venv`)
- **Node.js 20+** for the frontend
- **MongoDB Atlas** (the application database; Docker is optional for local-only MongoDB)
- **Playwright browsers**: `playwright install chromium`
- **`cookies.json`** at repo root (for Facebook scraping — export from a logged-in browser session)
- **`.env`** at repo root with Supabase PostgreSQL credentials:
  ```
  PG_HOST=<your-pooler-host>
  PG_PORT=6543
  PG_USER=postgres.<project-ref>
  PG_PASSWORD=<your-password>
  PG_DBNAME=postgres
  ```
- **`backend/.env`** with Supabase keys, PG credentials, and Google API key (see `backend/.env.example`)

## Setup

```bash
# 1. Create Supabase tables if using a new Supabase project (run in Supabase SQL Editor)
# Apply init_db.sql, then migrations in migrations/ in order, then views.sql

# 2. Create and activate the root Python environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install the complete Python environment
pip install -r requirements.txt

# 4. Install the Playwright browser
playwright install chromium

# 5. Install frontend dependencies
cd frontend && npm ci && cd ..

# 6. (Optional) Download ML models locally instead of fetching from HuggingFace
#    Place them in models/stage1_xlm_roberta_large/ and models/stage2_xlm_roberta_base/
```

## Running the Application

### Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

API available at `http://localhost:8000`. All endpoints require Supabase JWT auth.

### Frontend

```bash
cd frontend
npm run dev
```

Dashboard available at `http://localhost:3000`. Login with Supabase credentials.

### Data Pipeline (CLI)

All commands run from the **repo root** with `PYTHONPATH=src`.

When using MongoDB Atlas, do not start the local Docker MongoDB container. The
Atlas URI is read from `backend/.env` by the backend and pipeline modules.

#### Stage 1: Scrape

```bash
# Facebook (interactive menu)
PYTHONPATH=src python -m burmese_absa

# Facebook (non-interactive / Task Scheduler)
PYTHONPATH=src python -m burmese_absa --url https://www.facebook.com/<Page> --entity "<Name>" --max-posts 10 --headless

# Foodpanda
PYTHONPATH=src python -m burmese_absa --source foodpanda --url "https://www.foodpanda.com.mm/restaurant/..." --entity "<Name>" --headless

# Check tracking status
PYTHONPATH=src python -m burmese_absa --status

# JSON backfill (non-Facebook sources only)
PYTHONPATH=src python -m burmese_absa.ingest_to_mongo <file.json>
```

#### Stage 2: Clean

```bash
PYTHONPATH=src python -m burmese_absa.clean_feedbacks              # Clean unprocessed
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --reprocess  # Drop and re-clean all
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --status     # Show stats
```

#### Stage 3: ABSA Pipeline

```bash
PYTHONPATH=src python -m nlp.run_absa_pipeline                          # Both pipelines
PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline feedbacks     # Reviews only
PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline contents      # Posts only
PYTHONPATH=src python -m nlp.run_absa_pipeline --device cuda --batch-size 64  # GPU
PYTHONPATH=src python -m nlp.run_absa_pipeline --status                 # Show status
```

#### Stage 4: Export to Supabase

```bash
PYTHONPATH=src python -m nlp.export_to_postgres              # Export
PYTHONPATH=src python -m nlp.export_to_postgres --dry-run    # Preview
PYTHONPATH=src python -m nlp.export_to_postgres --status     # Row counts
```

## Backend API

All endpoints are under `/api/` and require `Authorization: Bearer <supabase-jwt>`.

### Entities (`/api/entities`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | List all tracked entities |
| GET | `/{entity_id}` | Get single entity |
| POST | `/` | Create entity |

### Brands (`/api/brands`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | List brand-to-entity mappings |
| POST | `/` | Create brand mapping |
| PUT | `/{brand_id}` | Update brand mapping |
| DELETE | `/{brand_id}` | Delete brand mapping |

### Analytics (`/api/analytics`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/overview` | Aggregate sentiment overview |
| GET | `/entities` | Per-entity sentiment overviews |
| GET | `/entities/{entity_id}` | Single entity detail |
| GET | `/aspects` | ABSA aspect breakdown |
| GET | `/trends` | Sentiment trend time-series |
| GET | `/kpis` | Dashboard KPIs |
| GET | `/engagement` | Facebook engagement metrics |
| GET | `/engagement/reactions` | Reaction type mix |
| GET | `/engagement/trends` | Engagement trend time-series |
| GET | `/drivers` | Top sentiment drivers |
| GET | `/reviews/flagged` | Flagged negative reviews |
| GET | `/benchmark` | Competitor benchmark comparison |

### ETL (`/api/etl`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/run` | Trigger full ETL pipeline |
| POST | `/clean` | Trigger clean stage only |
| POST | `/absa` | Trigger ABSA stage only |
| POST | `/export` | Trigger export stage only |
| GET | `/status` | Current pipeline status |
| GET | `/health` | System health snapshot |
| GET | `/history` | Recent ETL run history |

### Chat (`/api/chat`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/query` | Natural language question (non-streaming) |
| POST | `/stream` | Streaming NDJSON response |
| GET | `/history` | Conversation history |
| DELETE | `/history` | Clear conversation history |

### Mining (`/api/mining`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/association-rules` | Association rule mining results |
| GET | `/clusters` | Entity cluster analysis |
| POST | `/run` | Run both mining algorithms |

### Scraping (`/api/scraping`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/run` | Queue a new scrape job |
| GET | `/status/{run_id}` | Scrape run status |
| GET | `/events/{run_id}` | SSE progress stream |
| POST | `/cancel/{run_id}` | Request cancellation |
| GET | `/history` | Recent scrape history |
| GET | `/detect` | Auto-detect source from URL |
| GET | `/entities` | List saved scrape targets |
| POST | `/entities` | Create saved target |
| PUT | `/entities/{entity_id}` | Update saved target |
| DELETE | `/entities/{entity_id}` | Delete saved target |
| POST | `/entities/{entity_id}/run` | Re-scrape saved target |
| GET | `/schedules` | List cron schedules |
| POST | `/schedules` | Create/update schedule |
| DELETE | `/schedules/{schedule_id}` | Delete schedule |
| GET | `/readiness` | Check scrape prerequisites |
| GET | `/cookies` | Check cookies.json status |
| POST | `/cookies` | Upload cookies.json |

### Health

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | API health check |

## MongoDB Collections

All in database `feedback_analytics`:

| Collection | Source | Description |
|---|---|---|
| `contents` | Scrapers | Posts, reviews, articles (parent documents) |
| `feedbacks` | Scrapers | Comments and reviews (child documents) |
| `cleaned_contents` | `clean_feedbacks.py` | Cleaned post/review text |
| `cleaned_feedbacks` | `clean_feedbacks.py` | Cleaned comment/review text |
| `absa_processed_contents` | `run_absa_pipeline.py` | Posts with detected aspects |
| `absa_processed_feedbacks` | `run_absa_pipeline.py` | Reviews with aspect-sentiment pairs |

## PostgreSQL Star Schema (Supabase)

| Table | Description |
|---|---|
| `dim_entities` | Dimension: shops and pages (entity_name, platform, metadata) |
| `dim_brands` | Brand-to-Facebook-page mapping |
| `bridge_brand_foodpanda_shops` | Brand-to-Foodpanda-shop many-to-many |
| `fact_social_posts` | Facebook posts with reactions + ABSA-promoted aspects |
| `fact_review_absa_results` | Review ABSA results in long format |
| `etl_runs` | Pipeline audit log |
| `scrape_entities` | Saved scrape targets (owner-scoped, RLS) |
| `scrape_runs` | Live scrape progress (RLS) |
| `scrape_schedules` | Cron schedules with IANA timezone (RLS) |

Views (`views.sql`): `v_entity_sentiment_overview`, `v_aspect_breakdown`, and others power analytics API endpoints.

## Frontend Pages

| Route | Description |
|---|---|
| `/dashboard` | Main analytics dashboard (KPIs, trends, radar, aspects, engagement, drivers) |
| `/entities` | Entity list with platform filter + brand mapping settings |
| `/entities/[id]` | Entity detail (KPI cards, aspect breakdown, recent reviews) |
| `/analytics` | Overview tab (sentiment, aspects, engagement) + Benchmark tab |
| `/chat` | Chat with Data (streaming AI responses, inline charts, pinning, export) |
| `/mining` | Association rules + entity clusters |
| `/scraping` | Scrape control center (wizard, active jobs, history) |
| `/login` | Supabase auth (sign in, sign up, forgot password) |

## NLP Models

| Model | Purpose | Architecture |
|---|---|---|
| `Fixaro/myanmar-absa-aspect-detection` | Stage 1: Multi-label aspect detection | XLM-RoBERTa Large, BCEWithLogitsLoss |
| `Fixaro/myanmar-absa-sentiment-classification` | Stage 2: Sentiment classification | XLM-RoBERTa Base, sentence-pair |

**6 ABSA aspects:** `product_or_service_quality`, `fulfillment_and_speed`, `price_and_value`, `digital_experience`, `customer_support`, `variety_and_availability`

**3 sentiment labels:** `Positive`, `Negative`, `Neutral`

Models are loaded from local `models/` directory if present, otherwise downloaded from HuggingFace Hub.

## Text Cleaning Pipeline

5-stage Burmese-aware cleaning in `clean_feedbacks.py`:

1. **Encoding detection** — Zawgyi vs Unicode identification (with `google_myanmar_tools` fallback)
2. **Noise removal** — URLs, mentions, HTML tags, control characters, zero-width chars, repeated chars, emojis
3. **Normalization** — Burmese digit translation, Unicode normalization, whitespace collapsing
4. **Language tagging** — Myanmar Unicode, Latin, mixed (Burglish) detection
5. **Quality gate** — Minimum length filter, non-empty after cleaning check

Only documents with `cleaning_status: "clean"` are passed to ABSA models. Original data is never modified.

## Testing

```bash
# Scraper tests (unittest, from repo root)
PYTHONPATH=src python -m unittest tests.test_facebook_posts
PYTHONPATH=src python -m unittest tests.test_foodpanda

# Backend tests (pytest, from backend/)
cd backend && python -m pytest tests/

# Frontend tests (node --test, from frontend/)
cd frontend && npm run test:mining && npm run test:analytics && npm run test:scraping

# Frontend verification
cd frontend && npm run lint && npm run build
```

## Key Conventions

- Facebook reaction counts: unknown categories are `None`, never `0`. Incomplete breakdowns never produce false-zero ratios
- Reaction keys: `("like", "love", "care", "haha", "wow", "sad", "angry")`
- Burmese text, digits, and month names are first-class — encoding forced to UTF-8 at startup
- `engagement_history` capped at 100 snapshots per post
- Facebook `facebook_data.json` is debug output only — never ingest via `ingest_to_mongo`
- 30-day lifecycle: posts within 30 days get engagement updates; expired posts are finalized
- Dedup key: `_id = fb_post_<sha256(normalized_page_url + platform_content_id)>`

## Team Structure

| Member | Role | Focus |
|---|---|---|
| 1 | Data Engineering Lead | Scrapers, MongoDB, anti-ban |
| 2 | ML Engineer | Burmese NLP, ABSA model training |
| 3 | Data Warehouse Architect | ETL, PostgreSQL Star Schema |
| 4 | Data Scientist | Apriori, K-Means, clustering |
| 5 | AI Agent & Backend Dev | FastAPI, LangChain, Text-to-SQL |
| 6 | Frontend Developer | React/Next.js dashboard, BI viz |

## Documentation

- [Capstone Project Spec](docs/CAPSTONE_PROJECT.md) — Full project overview, syllabus mapping, milestones
- [Database Design](docs/Project_Database_Design.md) — PostgreSQL star schema DDL and ERD
- [UI/UX Architecture v3](docs/BI-NLP-Dashboard-UIUX-Architecture-v3.md) — Frontend component library, color system, and interaction rules
- [ETL & Scrape Management](docs/etl-scrape-management.md) — ETL health, scrape scheduling, concurrency controls
- [Implementation Plan](docs/implementation_plan.md) — Phased delivery plan (all 5 phases implemented)
- [Task Assignments](docs/TASK_ASSIGNMENTS.md) — Team member task ownership
