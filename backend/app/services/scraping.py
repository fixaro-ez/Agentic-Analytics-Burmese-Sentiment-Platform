from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ..config import settings
from ..database import get_pool
from ..models.scraping import (
    _validate_foodpanda_url,
    CookieStatus,
    SavedScrapeEntity,
    SavedScrapeEntityWrite,
    ScrapeDetectResponse,
    ScrapeReadiness,
    ScrapeRunHistory,
    ScrapeRunStatus,
    ScrapeSchedule,
    ScrapeScheduleWrite,
)

# ---------------------------------------------------------------------------
# Path setup — make the scraping package importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

MONGO_URI = settings.MONGO_URI
DB_NAME = "feedback_analytics"
COOKIE_PATH = REPO_ROOT / "cookies.json"
logger = logging.getLogger(__name__)
_active_scrape_tasks: set[asyncio.Task[None]] = set()
_scrape_tasks_by_run_id: dict[str, asyncio.Task[None]] = {}
_cancel_requests: set[str] = set()
_scheduler_task: asyncio.Task[None] | None = None


class ScrapePreflightError(RuntimeError):
    """Raised when a required local service or credential is unavailable."""


class ScrapeConflictError(RuntimeError):
    """Raised when the same source target already has an active scrape."""


class ScrapeNotFoundError(LookupError):
    """Raised when an owner-scoped scrape resource does not exist."""


class ScrapeCancelled(RuntimeError):
    """Internal cooperative-cancellation signal."""


def detect_scrape_target(url: str) -> ScrapeDetectResponse:
    """Detect supported source and a conservative entity-name suggestion."""
    raw = url.strip()
    try:
        parsed = urlparse(raw)
        hostname = (parsed.hostname or "").casefold()
        path = unquote(parsed.path).strip("/")
    except (ValueError, UnicodeError):
        return ScrapeDetectResponse(
            source=None,
            entity_name=None,
            supported=False,
            message="Enter a complete Facebook or Foodpanda URL.",
        )

    source: str | None = None
    if hostname == "facebook.com" or hostname.endswith(".facebook.com"):
        source = "facebook"
    elif "foodpanda." in hostname:
        source = "foodpanda"
    if source is None:
        return ScrapeDetectResponse(
            source=None,
            entity_name=None,
            supported=False,
            message="Only Facebook and Foodpanda URLs are supported.",
        )
    if source == "foodpanda":
        try:
            _validate_foodpanda_url(raw)
        except ValueError as exc:
            return ScrapeDetectResponse(
                source="foodpanda",
                entity_name=None,
                supported=False,
                message=str(exc),
            )

    segments = [part for part in path.split("/") if part]
    ignored = {
        "pages",
        "posts",
        "photos",
        "videos",
        "reel",
        "restaurant",
        "restaurants",
    }
    candidates = [part for part in segments if part.casefold() not in ignored]
    slug = candidates[-1] if source == "foodpanda" and candidates else (
        candidates[0] if candidates else ""
    )
    if source != "foodpanda":
        slug = re.sub(r"^[a-z0-9]{5,12}-", "", slug, flags=re.IGNORECASE)
    suggestion = re.sub(r"[-_.]+", " ", slug).strip()
    if suggestion and not any("\u1000" <= char <= "\u109f" for char in suggestion):
        suggestion = " ".join(word.capitalize() for word in suggestion.split())
    return ScrapeDetectResponse(
        source=source,
        entity_name=suggestion or None,
        supported=True,
        message=(
            "Source detected. Confirm the suggested entity name before saving."
            if suggestion
            else "Source detected. Enter the entity name used in analytics."
        ),
    )


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


# ---------------------------------------------------------------------------
# MongoDB helper (sync, used inside asyncio.to_thread)
# ---------------------------------------------------------------------------

def _get_mongo_client(timeout_ms: int = 2000) -> MongoClient:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=timeout_ms)
    try:
        client.admin.command("ping")
    except BaseException:
        client.close()
        raise
    return client


def _format_scrape_error(exc: BaseException) -> str:
    """Always return an actionable message, including for blank exceptions."""
    if isinstance(exc, NotImplementedError):
        return (
            "Playwright could not start under the current Windows event loop. "
            "Restart the backend after applying the scraper worker fix."
        )
    if isinstance(exc, PyMongoError):
        return (
            "MongoDB is unavailable. Start it with 'docker-compose up -d', "
            "then retry the scrape."
        )
    message = str(exc).strip()
    return message or f"{type(exc).__name__} (no error message was provided)"


def _normalize_stored_error(
    status: str,
    error: str | None,
    stats: dict[str, Any] | None = None,
) -> str | None:
    """Make legacy run errors readable without rewriting audit history."""
    if status != "failed":
        return error

    if stats and stats.get("source") == "facebook":
        raw_url = str(stats.get("url") or "").strip()
        try:
            decoded_path = unquote(urlparse(raw_url).path)
        except ValueError:
            decoded_path = ""
        if raw_url and any(character.isspace() for character in decoded_path):
            return (
                f"Invalid Facebook page URL: {raw_url}. Facebook page usernames "
                "cannot contain spaces. Use the exact page address, such as "
                "https://www.facebook.com/LotteriaMyanmar."
            )

    message = (error or "").strip()
    if not message:
        return (
            "This legacy run failed before the previous backend recorded error "
            "details. The fast failure matched the fixed Windows Playwright "
            "event-loop issue."
        )
    if "localhost:27017" in message and (
        "No connection could be made" in message or "actively refused" in message
    ):
        return (
            "MongoDB was unavailable. Start it with 'docker-compose up -d', "
            "wait for mongodb_staging, then retry."
        )
    return message


async def get_scrape_readiness(source: str) -> ScrapeReadiness:
    """Check local prerequisites without creating a failed run record."""
    try:
        client = await asyncio.to_thread(_get_mongo_client)
        client.close()
        mongodb_ready = True
    except PyMongoError:
        mongodb_ready = False

    cookies_ready: bool | None = None
    cookie_message = ""
    if source == "facebook":
        cookie_status = check_facebook_cookies()
        cookies_ready = cookie_status.valid
        cookie_message = cookie_status.message

    required_model_dirs = ["stage1_xlm_roberta_large"]
    if source == "foodpanda":
        required_model_dirs.append("stage2_xlm_roberta_base")
    required_model_files = ("config.json", "model.safetensors", "tokenizer.json")
    models_ready = all(
        all(
            (REPO_ROOT / "models" / folder / filename).is_file()
            for filename in required_model_files
        )
        for folder in required_model_dirs
    )
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        postgres_ready = True
    except Exception:
        postgres_ready = False
    pipeline_ready = models_ready and postgres_ready
    if not models_ready:
        pipeline_message = (
            "Required local ABSA model files are missing from the models folder."
        )
    elif not postgres_ready:
        pipeline_message = (
            "PostgreSQL is unavailable. Check the backend PG_* configuration."
        )
    else:
        pipeline_message = "Cleaning, ABSA, and PostgreSQL export are ready."

    ready = mongodb_ready and cookies_ready is not False
    if not mongodb_ready:
        message = (
            "MongoDB is not reachable. Run 'docker-compose up -d' from the "
            "repository root and wait for the mongodb_staging container."
        )
    elif cookies_ready is False:
        message = cookie_message
    else:
        message = "Scraper prerequisites are ready."

    return ScrapeReadiness(
        source=source,
        ready=ready,
        mongodb_ready=mongodb_ready,
        cookies_ready=cookies_ready,
        pipeline_ready=pipeline_ready,
        postgres_ready=postgres_ready,
        models_ready=models_ready,
        pipeline_message=pipeline_message,
        message=message,
    )


# ---------------------------------------------------------------------------
# ETL run tracking (reuses the etl_runs table)
# ---------------------------------------------------------------------------

async def _ensure_table() -> None:
    """Create etl_runs table if it doesn't exist yet."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS etl_runs ("
            "  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  run_type VARCHAR(30) NOT NULL,"
            "  status VARCHAR(20) NOT NULL DEFAULT 'running',"
            "  started_at TIMESTAMPTZ DEFAULT NOW(),"
            "  completed_at TIMESTAMPTZ,"
            "  duration_seconds FLOAT,"
            "  stats JSONB,"
            "  error TEXT,"
            "  triggered_by UUID"
            ")"
        )


async def _create_run(
    run_type: str,
    user_id: str | None,
    meta: dict | None = None,
    *,
    saved_entity_id: str | None = None,
    run_full_pipeline: bool = True,
    trigger_kind: str = "manual",
) -> str:
    """Insert a new run record and return its UUID as a string."""
    await _ensure_table()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            run_id = await conn.fetchval(
                "INSERT INTO etl_runs (run_type, status, stats, triggered_by) "
                "VALUES ($1, 'queued', $2::jsonb, $3::uuid) "
                "RETURNING run_id::text",
                run_type,
                json.dumps(meta) if meta else None,
                user_id,
            )
            if user_id and meta:
                try:
                    await conn.execute(
                        "INSERT INTO scrape_runs "
                        "(run_id, created_by, entity_id, source, source_url, "
                        " display_name, status, phase, progress_percent, "
                        " run_full_pipeline, trigger_kind) "
                        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, "
                        " 'queued', 'queued', 0, $7, $8)",
                        run_id,
                        user_id,
                        saved_entity_id,
                        meta["source"],
                        meta["url"],
                        meta["entity_name"],
                        run_full_pipeline,
                        trigger_kind,
                    )
                except Exception as exc:
                    if getattr(exc, "sqlstate", None) == "23505":
                        raise ScrapeConflictError(
                            "This source URL already has an active scrape. "
                            "Wait for it to finish or cancel it before retrying."
                        ) from exc
                    if getattr(exc, "sqlstate", None) == "42P01":
                        raise RuntimeError(
                            "Scrape-management tables are missing. Apply "
                            "migrations/20260801_etl_health_scrape_management.sql."
                        ) from exc
                    raise
    return run_id


async def _update_run_progress(
    run_id: str,
    *,
    status: str,
    phase: str,
    progress_percent: int,
    diagnostics: dict[str, Any] | None = None,
) -> None:
    pool = await get_pool()
    payload = {
        "phase": phase,
        "progress_percent": progress_percent,
        **(diagnostics or {}),
    }
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE etl_runs SET status = $2, "
                "stats = COALESCE(stats, '{}'::jsonb) || $3::jsonb "
                "WHERE run_id::text = $1",
                run_id,
                status,
                json.dumps(payload),
            )
            await conn.execute(
                "UPDATE scrape_runs SET status = $2, phase = $3, "
                "progress_percent = $4, updated_at = NOW(), "
                "diagnostics = diagnostics || $5::jsonb "
                "WHERE run_id::text = $1",
                run_id,
                status,
                phase,
                progress_percent,
                json.dumps(diagnostics or {}),
            )


async def _finish_run(
    run_id: str, status: str, stats: dict | None = None, error: str | None = None
) -> None:
    """Update a run record with final status, duration, stats, and error."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            management_row = await conn.fetchrow(
                "SELECT cancellation_requested FROM scrape_runs "
                "WHERE run_id::text = $1 FOR UPDATE",
                run_id,
            )
            if management_row and management_row["cancellation_requested"]:
                status = "cancelled"
                error = error or "Cancelled by an analyst."
            await conn.execute(
                "UPDATE etl_runs SET status = $2::text, completed_at = NOW(), "
                "  duration_seconds = EXTRACT(EPOCH FROM NOW() - started_at), "
                "  stats = COALESCE(stats, '{}'::jsonb) || "
                "          COALESCE($3::jsonb, '{}'::jsonb), error = $4 "
                "WHERE run_id::text = $1",
                run_id,
                status,
                json.dumps(stats) if stats else None,
                error,
            )
            await conn.execute(
                "UPDATE scrape_runs SET status = $2::text, phase = $3::text, "
                "progress_percent = CASE WHEN $2::text IN ('completed','partial','cancelled','failed') "
                "THEN 100 ELSE progress_percent END, "
                "updated_at = NOW(), diagnostics = diagnostics || "
                "COALESCE($4::jsonb, '{}'::jsonb) WHERE run_id::text = $1",
                run_id,
                status,
                "cancelled" if status == "cancelled" else status,
                json.dumps(stats) if stats else None,
            )
            await conn.execute(
                "UPDATE scrape_entities se SET last_scraped_at = NOW(), "
                "last_scrape_status = $2::text, last_scrape_error = $3::text, updated_at = NOW() "
                "FROM scrape_runs sr "
                "WHERE sr.run_id::text = $1 AND sr.entity_id = se.id",
                run_id,
                status,
                error,
            )


async def _wait_for_etl_run(
    run_id: str,
    timeout_seconds: float = 900,
    parent_scrape_run_id: str | None = None,
) -> None:
    """Wait until downstream data is exported before declaring scrape success."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        if parent_scrape_run_id and parent_scrape_run_id in _cancel_requests:
            raise ScrapeCancelled("Cancellation requested")
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, error FROM etl_runs WHERE run_id::text = $1",
                run_id,
            )
        if row is None:
            raise RuntimeError(f"ETL run {run_id} disappeared")
        if row["status"] == "completed":
            return
        if row["status"] == "failed":
            raise RuntimeError(
                f"ETL run failed: {row['error'] or 'no error details recorded'}"
            )
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(
                f"ETL run {run_id} did not finish within {timeout_seconds:.0f}s"
            )
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Facebook scrape (async — called directly, NOT via CLI wrapper)
# ---------------------------------------------------------------------------

async def _run_facebook_async(
    url: str, entity_name: str, max_posts: int, headless: bool
) -> dict[str, Any]:
    """
    Run the async Facebook scraper directly.
    We import the lower-level function and manage the DB connection ourselves.
    """
    from burmese_absa.scraping.facebook import run_facebook_page_scrape

    client = _get_mongo_client(timeout_ms=5000)
    db = client[DB_NAME]
    try:
        results = await run_facebook_page_scrape(
            db=db,
            page_url=url,
            entity_name=entity_name,
            max_posts=max_posts,
            cookie_path=str(COOKIE_PATH),
            headless=headless,
        )
        report_path = COOKIE_PATH.parent / "facebook_run_report.json"
        report: dict[str, Any] = {}
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        discovered = int(report.get("discovered_posts", len(results)) or 0)
        errors = report.get("errors") if isinstance(report.get("errors"), list) else []
        mongo_stats = report.get("mongo") if isinstance(report.get("mongo"), dict) else {}
        return {
            "posts_requested": max_posts,
            "posts_discovered": discovered,
            "posts_scraped": len(results),
            "posts_failed": len(errors),
            "mongo_inserted": int(mongo_stats.get("inserted", 0) or 0),
            "mongo_updated": int(mongo_stats.get("modified", 0) or 0),
        }
    finally:
        client.close()


def _run_facebook_worker(
    url: str, entity_name: str, max_posts: int, headless: bool
) -> dict[str, Any]:
    """
    Run Playwright on its own subprocess-capable event loop.

    Uvicorn's Windows reload process uses a selector loop, which cannot create
    subprocesses and makes async Playwright fail with a blank
    NotImplementedError. A dedicated ProactorEventLoop supports subprocesses
    without changing the API server's running loop.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _run_facebook_async(url, entity_name, max_posts, headless)
        )
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


# ---------------------------------------------------------------------------
# Foodpanda scrape (sync Playwright, wrapped in a thread)
# ---------------------------------------------------------------------------

def _run_foodpanda_sync(url: str, entity_name: str, headless: bool) -> dict[str, Any]:
    """Sync Foodpanda scrape — runs inside asyncio.to_thread."""
    from playwright.sync_api import sync_playwright
    from burmese_absa.scraping.foodpanda import (
        scrape_foodpanda_reviews,
        scrape_foodpanda_reviews_api,
    )
    from burmese_absa.scraping._config import (
        FOODPANDA_BROWSER_LOCALE,
        FOODPANDA_BROWSER_TIMEZONE,
        FOODPANDA_BROWSER_USER_AGENT,
    )
    from burmese_absa.scraping.storage import session_data
    from burmese_absa.scraping.lifecycle import (
        save_session_data_to_mongo,
    )

    session_data.clear()
    client = _get_mongo_client(timeout_ms=5000)
    db = client[DB_NAME]
    try:
        try:
            content = scrape_foodpanda_reviews_api(url, entity_name)
        except Exception as api_exc:
            logger.warning(
                "Foodpanda reviews API failed for %s; using browser fallback: %s",
                url,
                _format_worker_error(api_exc),
            )
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context(
                    user_agent=FOODPANDA_BROWSER_USER_AGENT,
                    locale=FOODPANDA_BROWSER_LOCALE,
                    timezone_id=FOODPANDA_BROWSER_TIMEZONE,
                    viewport={"width": 1440, "height": 1000},
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                try:
                    content = scrape_foodpanda_reviews(
                        context.new_page(), url, entity_name
                    )
                finally:
                    context.close()
                    browser.close()

        # Save in-memory session data to MongoDB
        mongo_stats = save_session_data_to_mongo(db)
        return {
            "reviews_scraped": len(content.get("feedbacks", [])),
            "contents_scraped": 1,
            **mongo_stats,
        }
    finally:
        session_data.clear()
        client.close()


# ---------------------------------------------------------------------------
# Public API — called by the router
# ---------------------------------------------------------------------------

async def start_scrape(
    source: str,
    url: str,
    entity_name: str,
    max_posts: int,
    headless: bool,
    user_id: str | None = None,
    run_full_pipeline: bool = True,
    saved_entity_id: str | None = None,
    trigger_kind: str = "manual",
) -> str:
    """
    Start a scrape job in the background. Returns run_id immediately.
    Follows the same fire-and-forget pattern as ETL services.
    """
    readiness = await get_scrape_readiness(source)
    if not readiness.ready:
        raise ScrapePreflightError(readiness.message)
    if run_full_pipeline and readiness.pipeline_ready is False:
        raise ScrapePreflightError(
            readiness.pipeline_message
            or "Cleaning, ABSA, and PostgreSQL export are unavailable."
        )

    meta = {"source": source, "url": url, "entity_name": entity_name}
    run_id = await _create_run(
        run_type=f"scrape_{source}",
        user_id=user_id,
        meta=meta,
        saved_entity_id=saved_entity_id,
        run_full_pipeline=run_full_pipeline,
        trigger_kind=trigger_kind,
    )
    managed = user_id is not None

    async def _execute() -> None:
        start = time.time()
        stats: dict[str, Any] = dict(meta)
        phase = "scrape"
        try:
            if managed:
                await _update_run_progress(
                    run_id,
                    status="running",
                    phase="scraping",
                    progress_percent=10,
                )
            if source == "facebook":
                scrape_stats = await asyncio.to_thread(
                    _run_facebook_worker,
                    url,
                    entity_name,
                    max_posts,
                    headless,
                )
            elif source == "foodpanda":
                scrape_stats = await asyncio.to_thread(
                    _run_foodpanda_sync, url, entity_name, headless
                )
            else:
                raise ValueError(f"Unknown source: {source}")
            stats.update(scrape_stats)
            if run_id in _cancel_requests:
                raise ScrapeCancelled("Cancellation requested")
            if managed:
                await _update_run_progress(
                    run_id,
                    status="running",
                    phase="persisted_to_mongodb",
                    progress_percent=65,
                    diagnostics=scrape_stats,
                )

            # Auto-trigger full ETL pipeline (Clean → ABSA → Export)
            if run_full_pipeline:
                phase = "etl"
                if managed:
                    await _update_run_progress(
                        run_id,
                        status="running",
                        phase="nlp_and_postgres",
                        progress_percent=75,
                    )
                from .etl import run_full_etl

                etl_run_id = await run_full_etl(
                    reprocess=False,
                    threshold=0.5,
                    user_id=user_id,
                    target="contents" if source == "facebook" else "feedbacks",
                )
                stats["etl_run_id"] = etl_run_id
                await _wait_for_etl_run(
                    etl_run_id,
                    parent_scrape_run_id=run_id,
                )
                stats["etl_status"] = "completed"
            else:
                stats["etl_status"] = "not_requested"

            elapsed = time.time() - start
            stats["duration"] = round(elapsed, 2)
            terminal_status = "completed"
            if source == "facebook" and stats.get("posts_scraped", 0) < max_posts:
                terminal_status = "partial"
                stats["warning"] = (
                    f"Requested {max_posts} posts, discovered "
                    f"{stats.get('posts_discovered', 0)}, and saved "
                    f"{stats.get('posts_scraped', 0)}."
                )
            if run_id in _cancel_requests:
                raise ScrapeCancelled("Cancellation requested")
            await _finish_run(run_id, terminal_status, stats=stats)
        except ScrapeCancelled:
            stats.update({"phase": phase, "cancellation_requested": True})
            await _finish_run(
                run_id,
                "cancelled",
                stats=stats,
                error="Cancelled by an analyst.",
            )
        except asyncio.CancelledError as exc:
            stats.update({"phase": phase, "error_type": type(exc).__name__})
            await _finish_run(
                run_id,
                "failed",
                stats=stats,
                error="Scrape stopped because the backend process was reloaded or shut down.",
            )
            raise
        except Exception as e:
            error = _format_scrape_error(e)
            stats.update({"phase": phase, "error_type": type(e).__name__})
            logger.exception("Scrape run %s failed during %s", run_id, phase)
            await _finish_run(run_id, "failed", stats=stats, error=error)
        finally:
            _cancel_requests.discard(run_id)
            _scrape_tasks_by_run_id.pop(run_id, None)

    task = asyncio.create_task(_execute())
    _active_scrape_tasks.add(task)
    task.add_done_callback(_active_scrape_tasks.discard)
    _scrape_tasks_by_run_id[run_id] = task
    return run_id


async def get_scrape_status(
    run_id: str, user_id: str | None = None
) -> ScrapeRunStatus | None:
    """Fetch a single scrape run's status by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT er.run_id::text, er.run_type, er.status, "
            "  er.started_at::text, er.completed_at::text, er.duration_seconds, "
            "  er.stats, er.error, sr.phase, sr.progress_percent, "
            "  sr.cancellation_requested, sr.entity_id::text AS saved_entity_id "
            "FROM etl_runs er LEFT JOIN scrape_runs sr ON sr.run_id = er.run_id "
            "WHERE er.run_id::text = $1 AND "
            "($2::uuid IS NULL OR er.triggered_by = $2::uuid OR er.triggered_by IS NULL)",
            run_id,
            user_id,
        )
    if row is None:
        return None

    stats = _json_dict(row["stats"]) or None
    etl_run_id = stats.get("etl_run_id") if stats else None
    return ScrapeRunStatus(
        run_id=row["run_id"],
        source=stats.get("source", row["run_type"].replace("scrape_", "")) if stats else row["run_type"].replace("scrape_", ""),
        entity_name=stats.get("entity_name", "") if stats else "",
        url=stats.get("url", "") if stats else "",
        status=row["status"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        duration_seconds=row["duration_seconds"],
        stats=stats,
        error=_normalize_stored_error(row["status"], row["error"], stats),
        etl_run_id=etl_run_id,
        phase=row["phase"] or (stats or {}).get("phase"),
        progress_percent=(
            row["progress_percent"]
            if row["progress_percent"] is not None
            else (stats or {}).get("progress_percent")
        ),
        cancellation_requested=bool(row["cancellation_requested"]),
        saved_entity_id=row["saved_entity_id"],
    )


async def get_scrape_history(
    limit: int = 20, user_id: str | None = None
) -> list[ScrapeRunHistory]:
    """Fetch recent scrape runs (newest first)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT run_id::text, run_type, status, "
            "  started_at::text, completed_at::text, duration_seconds, "
            "  stats, error "
            "FROM etl_runs "
            "WHERE run_type LIKE 'scrape_%' AND "
            "($2::uuid IS NULL OR triggered_by = $2::uuid OR triggered_by IS NULL) "
            "ORDER BY started_at DESC LIMIT $1",
            limit,
            user_id,
        )
    history: list[ScrapeRunHistory] = []
    for row in rows:
        stats = _json_dict(row["stats"]) or None
        history.append(
            ScrapeRunHistory(
                run_id=row["run_id"],
                run_type=row["run_type"],
                status=row["status"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                duration_seconds=row["duration_seconds"],
                stats=stats,
                error=_normalize_stored_error(
                    row["status"], row["error"], stats
                ),
            )
        )
    return history


async def list_saved_entities(user_id: str) -> list[SavedScrapeEntity]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id::text, dim_entity_id, source, source_url, display_name, "
            "max_posts, headless, auto_pipeline, created_at::text, updated_at::text, "
            "last_scraped_at::text, last_scrape_status, last_scrape_error "
            "FROM scrape_entities WHERE created_by = $1::uuid "
            "ORDER BY display_name, source",
            user_id,
        )
    return [SavedScrapeEntity(**dict(row)) for row in rows]


async def create_saved_entity(
    body: SavedScrapeEntityWrite, user_id: str
) -> SavedScrapeEntity:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "INSERT INTO scrape_entities "
                "(created_by, dim_entity_id, source, source_url, display_name, "
                " max_posts, headless, auto_pipeline) "
                "VALUES ($1::uuid, COALESCE($2, ("
                "  SELECT entity_id FROM dim_entities "
                "  WHERE LOWER(entity_name) = LOWER($5) AND platform = $3 LIMIT 1"
                ")), $3, $4, $5, $6, $7, $8) "
                "RETURNING id::text, dim_entity_id, source, source_url, display_name, "
                "max_posts, headless, auto_pipeline, created_at::text, updated_at::text, "
                "last_scraped_at::text, last_scrape_status, last_scrape_error",
                user_id,
                body.dim_entity_id,
                body.source,
                body.source_url,
                body.display_name,
                body.max_posts,
                body.headless,
                body.auto_pipeline,
            )
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise ScrapeConflictError(
                    "This URL is already saved. Edit the existing target instead."
                ) from exc
            raise
    return SavedScrapeEntity(**dict(row))


async def update_saved_entity(
    entity_id: str, body: SavedScrapeEntityWrite, user_id: str
) -> SavedScrapeEntity:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE scrape_entities SET dim_entity_id = COALESCE($3, ("
            "  SELECT entity_id FROM dim_entities "
            "  WHERE LOWER(entity_name) = LOWER($6) AND platform = $4 LIMIT 1"
            ")), source = $4, "
            "source_url = $5, display_name = $6, max_posts = $7, "
            "headless = $8, auto_pipeline = $9, updated_at = NOW() "
            "WHERE id::text = $1 AND created_by = $2::uuid "
            "RETURNING id::text, dim_entity_id, source, source_url, display_name, "
            "max_posts, headless, auto_pipeline, created_at::text, updated_at::text, "
            "last_scraped_at::text, last_scrape_status, last_scrape_error",
            entity_id,
            user_id,
            body.dim_entity_id,
            body.source,
            body.source_url,
            body.display_name,
            body.max_posts,
            body.headless,
            body.auto_pipeline,
        )
    if row is None:
        raise ScrapeNotFoundError("Saved scrape target not found")
    return SavedScrapeEntity(**dict(row))


async def delete_saved_entity(entity_id: str, user_id: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM scrape_entities "
            "WHERE id::text = $1 AND created_by = $2::uuid",
            entity_id,
            user_id,
        )
    return result.endswith("1")


async def run_saved_entity(entity_id: str, user_id: str) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id::text, source, source_url, display_name, max_posts, "
            "headless, auto_pipeline FROM scrape_entities "
            "WHERE id::text = $1 AND created_by = $2::uuid",
            entity_id,
            user_id,
        )
    if row is None:
        raise ScrapeNotFoundError("Saved scrape target not found")
    return await start_scrape(
        source=row["source"],
        url=row["source_url"],
        entity_name=row["display_name"],
        max_posts=row["max_posts"],
        headless=row["headless"],
        user_id=user_id,
        run_full_pipeline=row["auto_pipeline"],
        saved_entity_id=row["id"],
        trigger_kind="saved_entity",
    )


def _expand_cron_field(
    field: str, minimum: int, maximum: int, *, sunday_alias: bool = False
) -> set[int]:
    values: set[int] = set()
    for item in field.split(","):
        base, separator, step_text = item.partition("/")
        step = int(step_text) if separator else 1
        if step < 1:
            raise ValueError("cron steps must be positive")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(base)
        if not (minimum <= start <= maximum and minimum <= end <= maximum):
            raise ValueError("cron field is outside its allowed range")
        if end < start:
            raise ValueError("cron ranges cannot wrap")
        values.update(range(start, end + 1, step))
    if sunday_alias:
        return {0 if value == 7 else value for value in values}
    return values


def next_cron_time(
    expression: str,
    timezone_name: str,
    base: datetime | None = None,
) -> datetime:
    """Calculate the next standard five-field cron occurrence."""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron expression must have five fields")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    minute_values = _expand_cron_field(fields[0], 0, 59)
    hour_values = _expand_cron_field(fields[1], 0, 23)
    day_values = _expand_cron_field(fields[2], 1, 31)
    month_values = _expand_cron_field(fields[3], 1, 12)
    weekday_values = _expand_cron_field(fields[4], 0, 7, sunday_alias=True)
    day_is_wildcard = fields[2] == "*"
    weekday_is_wildcard = fields[4] == "*"

    current = (base or datetime.now(timezone.utc)).astimezone(zone)
    candidate = current.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(527_040):
        cron_weekday = (candidate.weekday() + 1) % 7
        day_match = candidate.day in day_values
        weekday_match = cron_weekday in weekday_values
        if day_is_wildcard:
            calendar_match = weekday_match
        elif weekday_is_wildcard:
            calendar_match = day_match
        else:
            calendar_match = day_match or weekday_match
        if (
            candidate.minute in minute_values
            and candidate.hour in hour_values
            and candidate.month in month_values
            and calendar_match
        ):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)
    raise ValueError("cron expression produced no run within the next year")


def _schedule_from_row(row: Any) -> ScrapeSchedule:
    return ScrapeSchedule(**dict(row))


async def list_schedules(user_id: str) -> list[ScrapeSchedule]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ss.id::text, ss.entity_id::text, ss.cron_expression, "
            "ss.timezone, ss.active, ss.created_at::text, ss.updated_at::text, "
            "ss.next_run::text, ss.last_run_at::text, se.display_name, se.source "
            "FROM scrape_schedules ss JOIN scrape_entities se ON se.id = ss.entity_id "
            "WHERE ss.created_by = $1::uuid ORDER BY se.display_name",
            user_id,
        )
    return [_schedule_from_row(row) for row in rows]


async def create_schedule(
    body: ScrapeScheduleWrite, user_id: str
) -> ScrapeSchedule:
    next_run = (
        next_cron_time(body.cron_expression, body.timezone)
        if body.active
        else None
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO scrape_schedules "
            "(created_by, entity_id, cron_expression, timezone, active, next_run) "
            "SELECT $1::uuid, se.id, $3, $4, $5, $6 "
            "FROM scrape_entities se "
            "WHERE se.id::text = $2 AND se.created_by = $1::uuid "
            "ON CONFLICT (created_by, entity_id) DO UPDATE SET "
            "cron_expression = EXCLUDED.cron_expression, timezone = EXCLUDED.timezone, "
            "active = EXCLUDED.active, next_run = EXCLUDED.next_run, updated_at = NOW() "
            "RETURNING id::text, entity_id::text, cron_expression, timezone, active, "
            "created_at::text, updated_at::text, next_run::text, last_run_at::text",
            user_id,
            body.entity_id,
            body.cron_expression,
            body.timezone,
            body.active,
            next_run,
        )
        if row is None:
            raise ScrapeNotFoundError("Saved scrape target not found")
        entity = await conn.fetchrow(
            "SELECT display_name, source FROM scrape_entities WHERE id = $1::uuid",
            row["entity_id"],
        )
    values = dict(row)
    values.update(dict(entity))
    return ScrapeSchedule(**values)


async def delete_schedule(schedule_id: str, user_id: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM scrape_schedules "
            "WHERE id::text = $1 AND created_by = $2::uuid",
            schedule_id,
            user_id,
        )
    return result.endswith("1")


async def cancel_scrape(run_id: str, user_id: str) -> str:
    status = await get_scrape_status(run_id, user_id)
    if status is None:
        raise ScrapeNotFoundError("Scrape run not found")
    if status.status in {"completed", "partial", "failed", "cancelled"}:
        return status.status
    _cancel_requests.add(run_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            updated = await conn.fetchval(
                "UPDATE scrape_runs SET status = 'cancelling', "
                "cancellation_requested = TRUE, updated_at = NOW() "
                "WHERE run_id::text = $1 AND created_by = $2::uuid "
                "AND status IN ('queued','running','cancelling') "
                "RETURNING run_id::text",
                run_id,
                user_id,
            )
            if updated:
                await conn.execute(
                    "UPDATE etl_runs SET status = 'cancelling', "
                    "stats = COALESCE(stats, '{}'::jsonb) || "
                    "'{\"cancellation_requested\":true}'::jsonb "
                    "WHERE run_id::text = $1 AND triggered_by = $2::uuid "
                    "AND status IN ('queued','running','cancelling')",
                    run_id,
                    user_id,
                )
    if not updated:
        current = await get_scrape_status(run_id, user_id)
        return current.status if current else "cancelled"
    task = _scrape_tasks_by_run_id.get(run_id)
    if task is None or task.done():
        await _finish_run(
            run_id,
            "cancelled",
            stats={"cancellation_requested": True},
            error="Cancelled after the worker process was no longer active.",
        )
        _cancel_requests.discard(run_id)
        return "cancelled"
    return "cancelling"


async def stream_scrape_events(run_id: str, user_id: str):
    """Yield owner-scoped status snapshots for an authenticated SSE response."""
    previous: str | None = None
    while True:
        status = await get_scrape_status(run_id, user_id)
        if status is None:
            raise ScrapeNotFoundError("Scrape run not found")
        payload = status.model_dump(mode="json")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if encoded != previous:
            previous = encoded
            yield encoded
        if status.status in {"completed", "partial", "failed", "cancelled"}:
            return
        await asyncio.sleep(1)


async def _run_due_schedules_once() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ss.id::text AS schedule_id, ss.created_by::text, "
            "ss.cron_expression, ss.timezone, se.id::text AS entity_id, "
            "se.source, se.source_url, se.display_name, se.max_posts, "
            "se.headless, se.auto_pipeline "
            "FROM scrape_schedules ss JOIN scrape_entities se ON se.id = ss.entity_id "
            "WHERE ss.active = TRUE AND ss.next_run <= NOW() "
            "ORDER BY ss.next_run LIMIT 10"
        )
    started = 0
    for row in rows:
        next_run = next_cron_time(row["cron_expression"], row["timezone"])
        async with pool.acquire() as conn:
            claimed = await conn.fetchval(
                "UPDATE scrape_schedules SET last_run_at = NOW(), next_run = $2, "
                "updated_at = NOW() WHERE id::text = $1 AND active = TRUE "
                "AND next_run <= NOW() RETURNING id::text",
                row["schedule_id"],
                next_run,
            )
        if not claimed:
            continue
        try:
            await start_scrape(
                source=row["source"],
                url=row["source_url"],
                entity_name=row["display_name"],
                max_posts=row["max_posts"],
                headless=row["headless"],
                user_id=row["created_by"],
                run_full_pipeline=row["auto_pipeline"],
                saved_entity_id=row["entity_id"],
                trigger_kind="schedule",
            )
            started += 1
        except (ScrapeConflictError, ScrapePreflightError) as exc:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE scrape_entities SET last_scrape_status = 'failed', "
                    "last_scrape_error = $2, updated_at = NOW() WHERE id::text = $1",
                    row["entity_id"],
                    str(exc),
                )
    return started


async def _scheduler_loop() -> None:
    while True:
        try:
            await _run_due_schedules_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled scrape poll failed")
        await asyncio.sleep(60)


def start_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())


async def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        await asyncio.gather(_scheduler_task, return_exceptions=True)
        _scheduler_task = None


def _validate_facebook_cookie_list(cookies: Any, *, exists: bool) -> CookieStatus:
    if not isinstance(cookies, list) or not cookies:
        return CookieStatus(
            exists=exists,
            valid=False,
            message="Invalid format: must be a non-empty array of cookies.",
        )

    required_fields = {"name", "value", "domain"}
    now = datetime.now(timezone.utc)
    expires_at: datetime | None = None
    active_facebook_names: set[str] = set()

    for index, cookie in enumerate(cookies):
        if not isinstance(cookie, dict):
            return CookieStatus(
                exists=exists,
                valid=False,
                message=f"Invalid cookie at index {index}: must be an object.",
            )
        missing = required_fields - set(cookie)
        if missing:
            return CookieStatus(
                exists=exists,
                valid=False,
                message=(
                    f"Invalid cookie at index {index}: missing fields "
                    f"{', '.join(sorted(missing))}."
                ),
            )

        raw_exp = cookie.get("expirationDate", cookie.get("expires", -1))
        try:
            exp = float(raw_exp)
        except (TypeError, ValueError):
            exp = -1
        if exp > 0:
            try:
                exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return CookieStatus(
                    exists=exists,
                    valid=False,
                    message=f"Invalid expiry on cookie at index {index}.",
                )
            if exp_dt <= now:
                continue
            if expires_at is None or exp_dt < expires_at:
                expires_at = exp_dt

        domain = str(cookie.get("domain", "")).lstrip(".").casefold()
        if domain == "facebook.com" or domain.endswith(".facebook.com"):
            active_facebook_names.add(str(cookie.get("name", "")))

    missing_critical = sorted({"c_user", "xs"} - active_facebook_names)
    if missing_critical:
        return CookieStatus(
            exists=exists,
            valid=False,
            expires_at=expires_at.isoformat() if expires_at else None,
            message=(
                "Facebook login cookies are expired, missing, or use the wrong "
                f"domain: {', '.join(missing_critical)}. Export fresh cookies."
            ),
        )

    return CookieStatus(
        exists=exists,
        valid=True,
        expires_at=expires_at.isoformat() if expires_at else None,
        message=f"Valid — {len(cookies)} cookies loaded.",
    )


def check_facebook_cookies() -> CookieStatus:
    """Check if cookies.json exists and contains active Facebook login cookies."""
    if not COOKIE_PATH.exists():
        return CookieStatus(
            exists=False,
            valid=False,
            message="cookies.json not found at repo root. Facebook scraping requires valid cookies.",
        )

    try:
        cookies = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
        return _validate_facebook_cookie_list(cookies, exists=True)
    except Exception as e:
        return CookieStatus(
            exists=True,
            valid=False,
            message=f"Error reading cookies.json: {e}",
        )


def upload_facebook_cookies(file_content: bytes) -> CookieStatus:
    """Upload and validate Facebook cookies.json file."""
    try:
        cookies = json.loads(file_content.decode("utf-8"))

        validation = _validate_facebook_cookie_list(cookies, exists=COOKIE_PATH.exists())
        if not validation.valid:
            return validation

        temporary_path = COOKIE_PATH.with_name(f"{COOKIE_PATH.name}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(cookies, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary_path.replace(COOKIE_PATH)
        finally:
            temporary_path.unlink(missing_ok=True)
        return _validate_facebook_cookie_list(cookies, exists=True)

    except json.JSONDecodeError as e:
        return CookieStatus(
            exists=False,
            valid=False,
            message=f"Invalid JSON: {e}",
        )
    except Exception as e:
        return CookieStatus(
            exists=False,
            valid=False,
            message=f"Upload failed: {e}",
        )
