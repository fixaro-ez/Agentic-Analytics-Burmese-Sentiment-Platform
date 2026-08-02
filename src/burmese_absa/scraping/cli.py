"""
Interactive CLI entry point for the scraping package.

Run with:
    python -m burmese_absa                    # interactive menu
    python -m burmese_absa --url ...          # non-interactive (cron-friendly)

The legacy entry point `python -m burmese_absa.scraping` also works.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from ._common import normalize_ui_text
from ._config import LIFECYCLE_DAYS
from .facebook import (
    _validate_facebook_cookies,
    migrate_facebook_schema,
    run_facebook_page_scrape,
)
from .foodpanda import (
    scrape_business_blog,
    scrape_foodpanda_reviews,
    scrape_foodpanda_reviews_api,
)
from ._config import (
    FOODPANDA_BROWSER_LOCALE,
    FOODPANDA_BROWSER_TIMEZONE,
    FOODPANDA_BROWSER_USER_AGENT,
)
from .lifecycle import get_db, save_session_data_to_mongo, show_tracking_status_db
from .storage import export_to_json, session_data

# Windows terminals may still expose a legacy CP1252 stream. Status messages
# contain Burmese text and emoji; a print failure must never abort post scraping.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# Resolve repo root so cookies.json (kept at the repo root) can be found
# regardless of the working directory.
REPO_ROOT = Path(__file__).resolve().parents[3]
COOKIE_PATH = REPO_ROOT / "cookies.json"

def run_facebook_scrape(target_url, entity_name, max_posts, headless=False):
    """Run the async Facebook post-metadata and reaction pipeline."""
    client, db = get_db()
    try:
        # Use REPO_ROOT to find cookies.json at the project root
        cookie_path = str(COOKIE_PATH)
        
        # Pre-validate cookies before launching browser
        total_cookies, valid_cookies, cookie_warnings = _validate_facebook_cookies(cookie_path)
        print(f"\n[INFO] Pre-flight cookie check: {valid_cookies}/{total_cookies} valid")
        for warning in cookie_warnings:
            print(f"[WARN] {warning}")
        
        if valid_cookies == 0:
            print(
                "\n[ERROR] No valid Facebook cookies found. "
                "Please sign in to Facebook and export fresh cookies."
            )
            return
        
        try:
            asyncio.run(run_facebook_page_scrape(
                db=db,
                page_url=target_url,
                entity_name=entity_name,
                max_posts=max_posts,
                cookie_path=cookie_path,
                headless=headless,
            ))
        except RuntimeError as exc:
            print(f"\n[ERROR] Facebook scrape stopped: {exc}")
            return
        show_tracking_status_db(db)
    finally:
        client.close()


def run_other_scrape(source, target_url, entity_name, headless=False):
    if not normalize_ui_text(target_url):
        raise ValueError(f'--url is required for source {source}')
    session_data.clear()
    client, db = get_db()
    try:
        if source == 'foodpanda':
            try:
                scrape_foodpanda_reviews_api(target_url, entity_name)
            except Exception as api_exc:
                print(
                    "[WARN] Foodpanda reviews API failed; "
                    f"falling back to browser extraction: {api_exc}"
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
                        scrape_foodpanda_reviews(
                            context.new_page(), target_url, entity_name
                        )
                    finally:
                        context.close()
                        browser.close()
        else:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                try:
                    page = browser.new_page()
                    if source == 'blog':
                        scrape_business_blog(page, target_url, entity_name)
                    else:
                        raise ValueError(f'Unsupported source: {source}')
                finally:
                    browser.close()
        save_session_data_to_mongo(db)
        export_to_json(entity_name or source)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Unified scraper: Facebook post metadata and reaction breakdowns are "
            f"refreshed during a {LIFECYCLE_DAYS}-day tracking window; "
            "expired posts are finalized. MongoDB (feedback_analytics.contents) is "
            "the source of truth — tracking_state.json is no longer used."
        )
    )
    parser.add_argument("--source", choices=('facebook', 'foodpanda', 'blog'), default='facebook',
                        help="Scraper source for --url (default: facebook)")
    parser.add_argument("--url", help="Source URL (enables non-interactive/cron mode)")
    parser.add_argument("--entity", default="", help="Business/Page/shop name (e.g. 'KFC Myanmar')")
    parser.add_argument("--max-posts", type=int, default=10,
                        help="Maximum number of posts to scan (default: 10)")
    parser.add_argument("--headless", action="store_true",
                        help="Run the browser headless (required for cron/Task Scheduler)")
    parser.add_argument("--status", action="store_true",
                        help="Show tracking status from MongoDB and exit")
    parser.add_argument(
        "--migrate-facebook-schema",
        action="store_true",
        help="Preview or run the Facebook post-only MongoDB migration",
    )
    parser.add_argument(
        "--confirm-delete-facebook-comments",
        action="store_true",
        help="Confirm permanent deletion during --migrate-facebook-schema",
    )
    args = parser.parse_args()

    if args.confirm_delete_facebook_comments and not args.migrate_facebook_schema:
        parser.error(
            "--confirm-delete-facebook-comments requires --migrate-facebook-schema"
        )

    if args.migrate_facebook_schema:
        client, db = get_db()
        try:
            report = migrate_facebook_schema(
                db, confirm_delete=args.confirm_delete_facebook_comments
            )
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            if report.get("dry_run"):
                print(
                    "[DRY RUN] Re-run with --confirm-delete-facebook-comments "
                    "to execute the migration."
                )
        finally:
            client.close()
        return

    # ── Non-interactive: --status (no browser needed) ──
    if args.status:
        client, db = get_db()
        try:
            show_tracking_status_db(db)
        finally:
            client.close()
        return

    # ── Non-interactive: --url (cron / Task Scheduler friendly, no input() prompts) ──
    # Example:
    #   python scraping.py --url https://www.facebook.com/LotteriaMyanmar --entity "Lotteria" --max-posts 10 --headless
    if args.url:
        if args.source == 'facebook':
            run_facebook_scrape(args.url, args.entity, args.max_posts, headless=args.headless)
        else:
            run_other_scrape(args.source, args.url, args.entity, headless=args.headless)
        return

    # ── Interactive mode ──
    print("==================================================")
    print("🚀 Unified Scraping CLI (with Facebook Auth)")
    print("==================================================")

    print("Select Source Type:")
    print(f"1. Facebook Page (Post metadata + reaction breakdown, "
          f"{LIFECYCLE_DAYS}-day lifecycle)")
    print("2. Foodpanda/Grab Shop (Reviews)")
    print("3. Business Blog (Articles)")
    print("4. 📊 View tracking status (MongoDB)")

    choice = input("Enter choice (1/2/3/4): ").strip()

    # ── Option 4: View status (no browser needed) ──
    if choice == '4':
        client, db = get_db()
        try:
            show_tracking_status_db(db)
        finally:
            client.close()
        return

    if choice not in ('1', '2', '3'):
        print("[ERROR] Invalid choice. Exiting.")
        return

    target_url = input("Enter the full URL: ").strip()
    entity_name = input("Enter Business/Page Name (e.g., KFC Myanmar): ").strip()

    # ── Option 1: Unified Facebook scrape ──
    if choice == '1':
        max_posts_input = input("Enter maximum number of posts to scrape (e.g., 10): ").strip()
        max_posts = int(max_posts_input) if max_posts_input.isdigit() else 10
        run_facebook_scrape(target_url, entity_name, max_posts, headless=False)
        return

    # ── Options 2/3: Other scrapers (unchanged) ──
    run_other_scrape('foodpanda' if choice == '2' else 'blog', target_url, entity_name, headless=False)

if __name__ == "__main__":
    main()
