# ETL Health and Scrape Management

## Implemented surfaces

The header sync badge opens a read-only **System & ETL Health** dialog. It
refreshes every 60 seconds and can be refreshed on demand. The dialog presents
the fixed pipeline:

`Scrapers → MongoDB → XLM-R NLP → Postgres DWH`

Each node reports an independent healthy, active, idle, stale, error, or
unavailable state. MongoDB and Postgres failures are isolated so a failed node
does not hide the remaining diagnostic information. The Postgres table lists
current warehouse row counts and the latest export delta when the run recorded
one.

The header **Scrape** action opens Scrape Manager.
`Cmd/Ctrl+Shift+S` opens the same drawer without adding shortcut text to the
button. The existing `/scraping` route remains available for backward
compatibility.

Scrape Manager includes:

- saved Facebook pages and Foodpanda shops with one-click re-scrape;
- a three-step source, URL, and options wizard;
- source detection and conservative entity-name suggestion from the URL;
- optional saved-source persistence and optional full ETL pipeline;
- phase progress over authenticated SSE, with three-second polling fallback;
- expandable history diagnostics and entity-aware dashboard deep links;
- cooperative cancellation and a database-enforced one-active-run-per-URL rule;
- five-field cron schedules interpreted in an IANA timezone.

Full processing is enabled by default for new manual and saved targets. An
analyst can still explicitly choose collection-only mode. A completed full run
now means all four stages succeeded:

`scrape → clean → ABSA → PostgreSQL reconciliation`

Cleaning fingerprints the raw fields that affect downstream output. ABSA
fingerprints the cleaned source state, model IDs, pipeline version, and
threshold. Consequently, a changed post body, review, rating, reaction count,
or threshold is reprocessed even when its MongoDB `_id` already exists.

Before a full scrape starts, the backend checks MongoDB, the required local
models, and PostgreSQL. After export it verifies that there are no unclean
documents, pending eligible ABSA documents, missing warehouse facts, or extra
warehouse facts. A non-zero backlog fails the ETL and parent scrape instead of
recording a false success.

Foodpanda targets must use a canonical restaurant route such as
`/restaurant/abcd/shop-name` (optionally prefixed by a language code or ending
in `/reviews`). The scraper extracts the four-character vendor code and
confirms it through Foodpanda's structured Myanmar reviews endpoint before
writing MongoDB. It collects up to 500 of the newest text reviews per run;
Foodpanda's displayed rating total can be much larger because it includes
rating-only submissions without review text. Browser extraction remains a
fallback for API changes. HTTP error pages, access-denied pages, redirects away
from the restaurant route, and unconfirmed vendor codes fail before any MongoDB
document is created.

Newly saved targets are linked automatically to an existing `dim_entities` row
when platform and case-insensitive entity name match. Analysts can leave the
link empty when no safe match exists.

## Supabase migration

Apply the additive migration before opening the new drawer:

```text
migrations/20260801_etl_health_scrape_management.sql
```

Existing installations should also apply:

```text
migrations/20260801_pipeline_default_and_integrity.sql
migrations/20260801_scrape_schedule_fk_index.sql
```

Run it in the Supabase SQL Editor, or through the project’s normal migration
deployment workflow. It creates:

- `scrape_entities`
- `scrape_runs`
- `scrape_schedules`

`etl_runs` remains the canonical and backward-compatible pipeline audit table.
`scrape_runs.run_id` references the same audit row instead of creating a second
run identity.

The migration enables Row Level Security. Saved targets, schedules, and run
reads are owner-scoped to `auth.uid()`. The FastAPI service also filters every
resource by the authenticated user to prevent IDOR access when it uses its
trusted PostgreSQL connection.

Windows needs packaged IANA data for `zoneinfo`; install updated dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## Scheduling operation

The scheduler is part of the FastAPI lifespan and checks due schedules every
60 seconds. Keep the backend running through Windows Task Scheduler or another
service manager. Database claiming prevents two backend workers from starting
the same due occurrence.

Supabase `pg_cron` can trigger database or HTTP work, but it cannot run the local
Playwright browser or reach a developer-only `localhost`. For this Windows-local
deployment the browser schedule executes in FastAPI; Supabase remains the
durable configuration and audit source.

## Known limitations

- Playwright calls are blocking inside dedicated worker threads. Cancellation
  is cooperative: it immediately prevents downstream NLP/export work, but an
  in-flight browser operation closes at its next safe worker checkpoint.
- Progress is phase-level, not per review or post, because the current scraper
  callbacks do not expose item-level progress.
- The local scheduler runs only while FastAPI is online. A production deployment
  should register the backend as an always-on Windows scheduled task/service.
- Facebook requires a valid repository-root `cookies.json`; both sources require
  MongoDB.
- Foodpanda's restaurant page currently blocks automated Playwright navigation,
  so the public structured reviews endpoint is the primary path. The latest 500
  text reviews are the per-run safety cap; diagnostics record available,
  extracted, rejected, and truncated counts.
- Existing audit rows with `triggered_by IS NULL` remain readable for backward
  compatibility. New rows record the authenticated user.
- The Escalation Queue and keyboard triage are intentionally not implemented.

## Security checks

- Every ETL and scrape-management route requires Supabase bearer authentication.
- Entity, schedule, status, history, cancellation, and SSE queries are
  owner-scoped server-side.
- Concurrent runs for the same owner/source/URL are rejected by a partial unique
  index, not only by UI state.
- Chat SQL still passes the server validator and executes inside a read-only
  PostgreSQL transaction.
