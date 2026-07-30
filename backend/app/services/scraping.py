from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from ..config import settings
from ..database import get_pool
from ..models.scraping import CookieStatus, ScrapeRunHistory, ScrapeRunStatus

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


# ---------------------------------------------------------------------------
# MongoDB helper (sync, used inside asyncio.to_thread)
# ---------------------------------------------------------------------------

def _get_mongo_client() -> MongoClient:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client


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


async def _create_run(run_type: str, user_id: str | None, meta: dict | None = None) -> str:
    """Insert a new run record and return its UUID as a string."""
    await _ensure_table()
    pool = await get_pool()
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            "INSERT INTO etl_runs (run_type, stats, triggered_by) "
            "VALUES ($1, $2::jsonb, $3::uuid) "
            "RETURNING run_id::text",
            run_type,
            json.dumps(meta) if meta else None,
            user_id,
        )
    return run_id


async def _finish_run(
    run_id: str, status: str, stats: dict | None = None, error: str | None = None
) -> None:
    """Update a run record with final status, duration, stats, and error."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE etl_runs SET status = $2, completed_at = NOW(), "
            "  duration_seconds = EXTRACT(EPOCH FROM NOW() - started_at), "
            "  stats = $3::jsonb, error = $4 "
            "WHERE run_id::text = $1",
            run_id,
            status,
            json.dumps(stats) if stats else None,
            error,
        )


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
    from burmese_absa.scraping.lifecycle import get_db as get_mongo_db

    client, db = get_mongo_db()
    try:
        results = await run_facebook_page_scrape(
            db=db,
            page_url=url,
            entity_name=entity_name,
            max_posts=max_posts,
            cookie_path=str(COOKIE_PATH),
            headless=headless,
        )
        return {"posts_scraped": len(results)}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Foodpanda scrape (sync Playwright, wrapped in a thread)
# ---------------------------------------------------------------------------

def _run_foodpanda_sync(url: str, entity_name: str, headless: bool) -> dict[str, Any]:
    """Sync Foodpanda scrape — runs inside asyncio.to_thread."""
    from playwright.sync_api import sync_playwright
    from burmese_absa.scraping.foodpanda import scrape_foodpanda_reviews
    from burmese_absa.scraping.storage import session_data
    from burmese_absa.scraping.lifecycle import (
        get_db as get_mongo_db,
        save_session_data_to_mongo,
    )

    client, db = get_mongo_db()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                scrape_foodpanda_reviews(page, url, entity_name)
            finally:
                browser.close()

        # Save in-memory session data to MongoDB
        save_session_data_to_mongo(db)
        count = len(session_data)
        session_data.clear()
        return {"reviews_scraped": count}
    finally:
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
) -> str:
    """
    Start a scrape job in the background. Returns run_id immediately.
    Follows the same fire-and-forget pattern as ETL services.
    """
    run_id = await _create_run(
        run_type=f"scrape_{source}",
        user_id=user_id,
        meta={"source": source, "url": url, "entity_name": entity_name},
    )

    async def _execute() -> None:
        start = time.time()
        try:
            if source == "facebook":
                stats = await _run_facebook_async(url, entity_name, max_posts, headless)
            elif source == "foodpanda":
                stats = await asyncio.to_thread(
                    _run_foodpanda_sync, url, entity_name, headless
                )
            else:
                raise ValueError(f"Unknown source: {source}")

            # Auto-trigger full ETL pipeline (Clean → ABSA → Export)
            from .etl import run_full_etl
            etl_run_id = await run_full_etl(
                reprocess=False, threshold=0.5, user_id=user_id
            )
            stats["etl_run_id"] = etl_run_id

            elapsed = time.time() - start
            stats["duration"] = round(elapsed, 2)
            await _finish_run(run_id, "completed", stats=stats)
        except Exception as e:
            await _finish_run(run_id, "failed", error=str(e))

    asyncio.create_task(_execute())
    return run_id


async def get_scrape_status(run_id: str) -> ScrapeRunStatus | None:
    """Fetch a single scrape run's status by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT run_id::text, run_type, status, "
            "  started_at::text, completed_at::text, duration_seconds, "
            "  stats, error "
            "FROM etl_runs WHERE run_id::text = $1",
            run_id,
        )
    if row is None:
        return None

    stats = json.loads(row["stats"]) if row["stats"] else None
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
        error=row["error"],
        etl_run_id=etl_run_id,
    )


async def get_scrape_history(limit: int = 20) -> list[ScrapeRunHistory]:
    """Fetch recent scrape runs (newest first)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT run_id::text, run_type, status, "
            "  started_at::text, completed_at::text, duration_seconds, "
            "  stats, error "
            "FROM etl_runs "
            "WHERE run_type LIKE 'scrape_%' "
            "ORDER BY started_at DESC LIMIT $1",
            limit,
        )
    return [
        ScrapeRunHistory(
            run_id=r["run_id"],
            run_type=r["run_type"],
            status=r["status"],
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            duration_seconds=r["duration_seconds"],
            stats=json.loads(r["stats"]) if r["stats"] else None,
            error=r["error"],
        )
        for r in rows
    ]


def check_facebook_cookies() -> CookieStatus:
    """Check if cookies.json exists and hasn't expired."""
    if not COOKIE_PATH.exists():
        return CookieStatus(
            exists=False,
            valid=False,
            message="cookies.json not found at repo root. Facebook scraping requires valid cookies.",
        )

    try:
        cookies = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
        if not isinstance(cookies, list) or len(cookies) == 0:
            return CookieStatus(
                exists=True,
                valid=False,
                message="cookies.json is empty or invalid format.",
            )

        # Check if any cookie has an expiry in the future
        now = datetime.now(timezone.utc)
        expires_at = None
        for cookie in cookies:
            exp = cookie.get("expires", -1)
            if exp > 0:
                exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
                if expires_at is None or exp_dt < expires_at:
                    expires_at = exp_dt

        if expires_at and expires_at < now:
            return CookieStatus(
                exists=True,
                valid=False,
                expires_at=expires_at.isoformat(),
                message=f"Cookies expired on {expires_at.strftime('%Y-%m-%d %H:%M UTC')}. Please refresh.",
            )

        return CookieStatus(
            exists=True,
            valid=True,
            expires_at=expires_at.isoformat() if expires_at else None,
            message=f"Valid — {len(cookies)} cookies loaded.",
        )
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

        if not isinstance(cookies, list) or len(cookies) == 0:
            return CookieStatus(
                exists=True,
                valid=False,
                message="Invalid format: must be a non-empty array of cookies.",
            )

        required_fields = {"name", "value", "domain"}
        for i, cookie in enumerate(cookies):
            if not isinstance(cookie, dict):
                return CookieStatus(
                    exists=True,
                    valid=False,
                    message=f"Invalid cookie at index {i}: must be an object.",
                )
            missing = required_fields - set(cookie.keys())
            if missing:
                return CookieStatus(
                    exists=True,
                    valid=False,
                    message=f"Invalid cookie at index {i}: missing fields {missing}.",
                )

        COOKIE_PATH.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        return check_facebook_cookies()

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
