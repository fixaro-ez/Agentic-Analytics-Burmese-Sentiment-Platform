# AGENTS.md

## Prerequisites

- **MongoDB** must be running before any scrape or test: `docker-compose up -d`
- **`cookies.json`** (gitignored) must exist at the **repo root** for Facebook scraping
- Python venv (`.venv`) already has `playwright` and `pymongo`; no `requirements.txt` or `pyproject.toml`
- Windows-only deployment (Task Scheduler, not cron)

## Commands

All commands are run from the **repo root**. The package lives in `src/burmese_absa/`.
The project uses a `src/` layout, so `PYTHONPATH=src` must be set so Python can
find the `burmese_absa` package (there is no `pyproject.toml` / `setup.py`).

```bash
# Start MongoDB
docker-compose up -d

# Run scraper (Facebook default)
PYTHONPATH=src python -m burmese_absa --url https://www.facebook.com/<Page> --entity "<Name>" --max-posts 10 --headless

# Run scraper (Foodpanda)
PYTHONPATH=src python -m burmese_absa --source foodpanda --url "<shop_url>" --entity "<Name>" --headless

# Run tests (unittest, no framework config)
PYTHONPATH=src python -m unittest tests.test_facebook_posts
PYTHONPATH=src python -m unittest tests.test_foodpanda

# Check tracking status
PYTHONPATH=src python -m burmese_absa --status

# Ingest JSON backfill (non-Facebook only)
PYTHONPATH=src python -m burmese_absa.ingest_to_mongo <file.json>

# Clean raw text for ABSA models (writes to cleaned_contents + cleaned_feedbacks)
PYTHONPATH=src python -m burmese_absa.clean_feedbacks                           # Clean unprocessed docs only
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --reprocess               # Drop and re-clean all
PYTHONPATH=src python -m burmese_absa.clean_feedbacks --status                  # Show cleaning stats
```

## Project Layout

```
Selenium/
├── src/burmese_absa/        # Python package
│   ├── __init__.py
│   ├── __main__.py          # `python -m burmese_absa` → CLI
│   ├── scraping/            # The unified scraper (split into submodules)
│   │   ├── __init__.py      # Re-exports all public symbols
│   │   ├── __main__.py      # `python -m burmese_absa.scraping` → CLI
│   │   ├── _config.py       # MongoDB URI, REACTION_KEYS, FOODPANDA_* constants
│   │   ├── _common.py       # Shared utility functions (timestamp parsers, normalizers)
│   │   ├── storage.py       # In-memory `session_data` + JSON export
│   │   ├── lifecycle.py     # 30-day MongoDB-backed lifecycle, get_db, indexes
│   │   ├── facebook.py      # Async Facebook post scraping + reaction breakdown + migration
│   │   ├── foodpanda.py     # Sync Foodpanda review scraping + business blog
│   │   └── cli.py           # argparse, run_facebook_scrape, run_other_scrape, main
│   ├── clean_feedbacks.py
│   └── ingest_to_mongo.py
├── tests/
│   ├── __init__.py
│   ├── test_facebook_posts.py
│   └── test_foodpanda.py
├── docs/
│   ├── CAPSTONE_PROJECT.md
│   └── Project_Database_Design.md
├── docker-compose.yaml
├── cookies.json             # gitignored, at repo root
├── AGENTS.md                # this file (kept at repo root for opencode discovery)
└── .gitignore
```

## Architecture

- **Single CLI entry point**: `python -m burmese_absa` invokes `burmese_absa.scraping.cli.main()`.
- **`burmese_absa.scraping`** is the unified scraper. It is a package split into focused submodules, but every public symbol that was importable from the original monolithic `scraping.py` is re-exported from `burmese_absa.scraping` for backward compatibility.
- **Facebook uses `async_playwright`**, Foodpanda/blog use `sync_playwright`. Both write to MongoDB.
- **`ingest_to_mongo.py`** is only for non-Facebook sources and backfills. The scraper writes to MongoDB directly for Facebook.
- **MongoDB** is the source of truth. Database: `feedback_analytics`, collections: `contents` (posts) and `feedbacks` (comments/reviews).
- **Dedup key**: Facebook posts use `_id = fb_post_<sha256(normalized_page_url + platform_content_id)>`.
- **30-day lifecycle**: Posts within 30 days get engagement-only updates on re-scrape; expired posts are marked `lifecycle_status: "final"` and skipped.
- **Derived metrics must always be recalculated** immediately before MongoDB writes. Never reuse grouped reactions from JSON input or prior scrape.
- **`clean_feedbacks.py`** is the text cleaning pipeline for ABSA. It reads `raw_text`/`title_or_post` from `contents` and `feedbacks`, applies 5-stage Burmese-aware cleaning (encoding detection, noise removal, normalization, language tagging, quality gate), and writes to **separate** `cleaned_contents` and `cleaned_feedbacks` collections. Original data is never modified. Only documents with `cleaning_status: "clean"` should be passed to the ABSA models.

## Testing Quirks

- `tests/test_foodpanda.py` **mocks all imports** (`playwright`, `pymongo`) at the top of the file because dependencies may not be installed in the test environment. Tests must work with these mocks.
- Tests use `unittest` — no pytest config, no test runner script.
- Facebook tests import pure functions from `burmese_absa.scraping` — no browser or DB needed.
- Foodpanda tests use `importlib.import_module('burmese_absa.scraping')` and `importlib.import_module('burmese_absa.ingest_to_mongo')` so the mocks at the top of the file apply. They also reference `FOODPANDA_REVIEW_MODAL`, `FOODPANDA_REVIEW_CARDS`, and `is_foodpanda_modal_open` — all re-exported from `burmese_absa.scraping`.

## Key Conventions

- Facebook reaction counts: unknown categories are `None`, never `0`. Incomplete breakdowns never produce false-zero ratios.
- Reaction keys: `("like", "love", "care", "haha", "wow", "sad", "angry")`
- Burmese text, digits, and month names are first-class — encoding is forced to UTF-8 at startup.
- `engagement_history` is capped at 100 snapshots per post (`MAX_ENGAGEMENT_HISTORY`).
- `facebook_data.json` is debug output only — never ingest it via `ingest_to_mongo` (freshness guard exists but don't risk it).
- **ABSA aspects** (6): `product_or_service_quality`, `fulfillment_and_speed`, `price_and_value`, `digital_experience`, `customer_support`, `variety_and_availability`.
