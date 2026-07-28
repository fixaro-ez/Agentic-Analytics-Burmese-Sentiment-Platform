# Burmese ABSA Analytics Platform

End-to-end data pipeline and Agentic AI platform for decoding Burmese sentiment in the Myanmar market. Extracts raw customer feedback from Facebook and Foodpanda, applies a custom two-stage Aspect-Based Sentiment Analysis (ABSA) model, stores results in a PostgreSQL star schema (Supabase), and surfaces insights via a BI dashboard with "Chat with Data" and AI-driven crisis alerts.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SCRAPE              CLEAN              ABSA                EXPORT       │
│                                                                          │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐    ┌─────────┐ │
│  │Facebook  │    │clean_        │    │run_absa_       │    │export_  │ │
│  │Foodpanda │───►│feedbacks.py  │───►│pipeline.py     │───►│to_      │ │
│  │Blog      │    │(5-stage)     │    │(2-stage ABSA)  │    │postgres │ │
│  └──────────┘    └──────────────┘    └────────────────┘    └────┬────┘ │
│       │               │                     │                    │       │
│       ▼               ▼                     ▼                    ▼       │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     MongoDB (Data Lake)                           │   │
│  │  contents → cleaned_contents → absa_processed_contents            │   │
│  │  feedbacks → cleaned_feedbacks → absa_processed_feedbacks         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Supabase (PostgreSQL Star Schema)                     │   │
│  │  dim_entities │ fact_social_posts │ fact_review_absa_results      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
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
| Backend (planned) | FastAPI, LangChain, LLM API |
| Frontend (planned) | React/Next.js, Tailwind CSS, shadcn/ui, Tremor, Recharts |
| Scheduling (planned) | Supabase Edge Functions + pg_cron |

## Project Structure

```
Selenium/
├── src/
│   ├── burmese_absa/                # Data ingestion package
│   │   ├── __init__.py
│   │   ├── __main__.py              # CLI entry: python -m burmese_absa
│   │   ├── scraping/                # Unified scraper
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
│       ├── __init__.py
│       ├── run_absa_pipeline.py     # 2-stage ABSA inference
│       └── export_to_postgres.py    # MongoDB → Supabase ETL
├── models/                          # Local ML model weights (gitignored)
│   ├── stage1_xlm_roberta_large/    # Aspect detection
│   └── stage2_xlm_roberta_base/     # Sentiment classification
├── tests/
│   ├── test_facebook_posts.py       # Pure function tests (no browser)
│   └── test_foodpanda.py            # Mocked Playwright + pymongo tests
├── docs/
│   ├── CAPSTONE_PROJECT.md          # Full capstone project spec
│   ├── Project_Database_Design.md   # PostgreSQL star schema design
│   └── BI-NLP-Dashboard-UIUX-Architecture-v3.md  # Frontend architecture
├── init_db.sql                      # Supabase DDL (star schema tables)
├── docker-compose.yaml              # MongoDB container
├── .env                             # Supabase PG credentials (gitignored)
├── cookies.json                     # Facebook auth cookies (gitignored)
└── AGENTS.md                        # AI agent coding instructions
```

## Prerequisites

- **Python 3.10+** with a virtual environment (`.venv`)
- **Docker** (for MongoDB container)
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

## Setup

```bash
# 1. Start MongoDB
docker-compose up -d

# 2. Create Supabase tables (run in Supabase SQL Editor)
# Copy and paste the contents of init_db.sql

# 3. Install Playwright browser
playwright install chromium

# 4. (Optional) Download ML models locally instead of fetching from HuggingFace
#    Place them in models/stage1_xlm_roberta_large/ and models/stage2_xlm_roberta_base/
```

## Usage

All commands run from the **repo root** with `PYTHONPATH=src`.

### Stage 1: Scrape

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

### Stage 2: Clean

```bash
# Clean unprocessed documents
PYTHONPATH=src python -m burmese_absa.clean_feedbacks

# Drop and re-clean all
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --reprocess

# Preview without writing
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --dry-run

# Show cleaning stats
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --status
```

### Stage 3: ABSA Pipeline

```bash
# Run both pipelines (feedbacks: Stage 1+2, contents: Stage 1 only)
PYTHONPATH=src python -m nlp.run_absa_pipeline

# Run one pipeline only
PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline feedbacks
PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline contents

# GPU acceleration
PYTHONPATH=src python -m nlp.run_absa_pipeline --device cuda --batch-size 64

# Drop and reprocess all
PYTHONPATH=src python -m nlp.run_absa_pipeline --reprocess

# Preview without writing
PYTHONPATH=src python -m nlp.run_absa_pipeline --dry-run

# Show pipeline status
PYTHONPATH=src python -m nlp.run_absa_pipeline --status
```

### Stage 4: Export to Supabase

```bash
# Export ABSA results to PostgreSQL star schema
PYTHONPATH=src python -m nlp.export_to_postgres

# Preview without writing
PYTHONPATH=src python -m nlp.export_to_postgres --dry-run

# Show PostgreSQL table row counts
PYTHONPATH=src python -m nlp.export_to_postgres --status
```

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
| `dim_entities` | Dimension table: shops and pages (entity_name, platform, metadata) |
| `fact_social_posts` | Facebook posts with reaction counts and ABSA-promoted aspects |
| `fact_review_absa_results` | Review ABSA results in long format (one row per aspect-sentiment pair) |

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
# Facebook tests (pure functions, no browser/DB needed)
PYTHONPATH=src python -m unittest tests.test_facebook_posts

# Foodpanda tests (mocked Playwright + pymongo)
PYTHONPATH=src python -m unittest tests.test_foodpanda
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
- [UI/UX Architecture v3](docs/BI-NLP-Dashboard-UIUX-Architecture-v3.md) — Frontend component library, color system, interaction rules, agentic features
