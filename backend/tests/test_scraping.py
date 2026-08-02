from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from pymongo.errors import ServerSelectionTimeoutError

from app.models.scraping import CookieStatus, ScrapeReadiness, ScrapeRequest
from app.services import scraping


class ScrapeRequestValidationTests(unittest.TestCase):
    def test_rejects_insecure_http_url(self):
        with self.assertRaisesRegex(ValueError, "https://"):
            ScrapeRequest(
                source="facebook",
                url="http://facebook.com/example",
                entity_name="Example",
            )

    def test_facebook_request_accepts_valid_page(self):
        request = ScrapeRequest(
            source="facebook",
            url=" https://www.facebook.com/LotteriaMyanmar ",
            entity_name=" Lotteria Myanmar ",
            max_posts=4,
        )
        self.assertEqual(
            request.url, "https://www.facebook.com/LotteriaMyanmar"
        )
        self.assertEqual(request.entity_name, "Lotteria Myanmar")

    def test_facebook_request_rejects_non_facebook_url(self):
        with self.assertRaises(ValidationError):
            ScrapeRequest(
                source="facebook",
                url="https://example.com/not-facebook",
                entity_name="Example",
            )

    def test_facebook_request_rejects_page_path_with_spaces(self):
        for url in (
            "https://www.facebook.com/Lotteria Myanmar",
            "https://www.facebook.com/Lotteria%20Myanmar",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(
                    ValidationError, "cannot contain spaces"
                ):
                    ScrapeRequest(
                        source="facebook",
                        url=url,
                        entity_name="Lotteria Myanmar",
                    )

    def test_facebook_request_rejects_home_page(self):
        with self.assertRaisesRegex(
            ValidationError, "must identify a page or post"
        ):
            ScrapeRequest(
                source="facebook",
                url="https://www.facebook.com/",
                entity_name="Example",
            )

    def test_request_rejects_out_of_range_post_count(self):
        with self.assertRaises(ValidationError):
            ScrapeRequest(
                source="facebook",
                url="https://facebook.com/example",
                entity_name="Example",
                max_posts=0,
            )

    def test_full_pipeline_is_default_at_api_boundary(self):
        request = ScrapeRequest(
            source="foodpanda",
            url="https://www.foodpanda.com.mm/restaurant/a1b2/example-shop",
            entity_name="Example",
        )
        self.assertTrue(request.run_full_pipeline)
        self.assertFalse(request.save_for_future)

    def test_url_detection_suggests_source_and_name(self):
        facebook = scraping.detect_scrape_target(
            "https://www.facebook.com/LotteriaMyanmar"
        )
        foodpanda = scraping.detect_scrape_target(
            "https://www.foodpanda.com.mm/restaurant/a1b2/lotteria-junction-city"
        )
        self.assertEqual(facebook.source, "facebook")
        self.assertEqual(facebook.entity_name, "Lotteriamyanmar")
        self.assertEqual(foodpanda.source, "foodpanda")
        self.assertEqual(foodpanda.entity_name, "Lotteria Junction City")

    def test_foodpanda_request_rejects_malformed_restaurant_route(self):
        with self.assertRaisesRegex(ValidationError, "must be a restaurant page"):
            ScrapeRequest(
                source="foodpanda",
                url=(
                    "https://www.foodpanda.com.mm/restaurant/"
                    "abcd1234-lotteria-junction-city"
                ),
                entity_name="Lotteria Junction City",
            )

    def test_detection_marks_malformed_foodpanda_route_unsupported(self):
        detected = scraping.detect_scrape_target(
            "https://www.foodpanda.com.mm/restaurant/"
            "abcd1234-lotteria-junction-city"
        )
        self.assertEqual(detected.source, "foodpanda")
        self.assertFalse(detected.supported)
        self.assertIsNone(detected.entity_name)

    def test_invalid_cookie_upload_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie_path = Path(directory) / "cookies.json"
            cookie_path.write_text("keep-me", encoding="utf-8")
            invalid = json.dumps(
                [
                    {"name": "c_user", "value": "1", "domain": "example.com"},
                    {"name": "xs", "value": "2", "domain": "example.com"},
                ]
            ).encode()

            with patch.object(scraping, "COOKIE_PATH", cookie_path):
                result = scraping.upload_facebook_cookies(invalid)

            self.assertFalse(result.valid)
            self.assertEqual(cookie_path.read_text(encoding="utf-8"), "keep-me")

    def test_valid_cookie_upload_is_written_after_validation(self):
        expiry = (datetime.now(timezone.utc) + timedelta(days=1)).timestamp()
        payload = json.dumps(
            [
                {
                    "name": "c_user",
                    "value": "1",
                    "domain": ".facebook.com",
                    "expirationDate": expiry,
                },
                {
                    "name": "xs",
                    "value": "2",
                    "domain": ".facebook.com",
                    "expirationDate": expiry,
                },
            ]
        ).encode()

        with tempfile.TemporaryDirectory() as directory:
            cookie_path = Path(directory) / "cookies.json"
            with patch.object(scraping, "COOKIE_PATH", cookie_path):
                result = scraping.upload_facebook_cookies(payload)

            self.assertTrue(result.valid)
            self.assertEqual(len(json.loads(cookie_path.read_text(encoding="utf-8"))), 2)


class ScrapingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        pending = list(scraping._active_scrape_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def test_readiness_reports_mongodb_failure(self):
        with (
            patch.object(
                scraping,
                "_get_mongo_client",
                side_effect=ServerSelectionTimeoutError("offline"),
            ),
            patch.object(
                scraping,
                "check_facebook_cookies",
                return_value=CookieStatus(
                    exists=True,
                    valid=True,
                    message="Cookies ready",
                ),
            ),
            patch.object(
                scraping,
                "get_pool",
                new=AsyncMock(side_effect=RuntimeError("postgres offline")),
            ),
        ):
            result = await scraping.get_scrape_readiness("facebook")

        self.assertFalse(result.ready)
        self.assertFalse(result.mongodb_ready)
        self.assertIn("docker-compose up -d", result.message)

    async def test_legacy_errors_are_normalized_for_history(self):
        blank = scraping._normalize_stored_error("failed", "")
        mongo = scraping._normalize_stored_error(
            "failed",
            "localhost:27017: [WinError 10061] No connection could be made",
        )

        self.assertIn("legacy run", blank.casefold())
        self.assertIn("docker-compose up -d", mongo)

    async def test_legacy_malformed_facebook_url_gets_exact_diagnosis(self):
        message = scraping._normalize_stored_error(
            "failed",
            "Facebook did not render any post permalinks after multiple attempts.",
            {
                "source": "facebook",
                "url": "https://www.facebook.com/Lotteria Myanmar",
            },
        )

        self.assertIn("cannot contain spaces", message)
        self.assertIn("https://www.facebook.com/LotteriaMyanmar", message)

    async def test_start_rejects_failed_preflight_before_creating_run(self):
        not_ready = ScrapeReadiness(
            source="facebook",
            ready=False,
            mongodb_ready=False,
            cookies_ready=True,
            message="MongoDB unavailable",
        )
        with (
            patch.object(
                scraping,
                "get_scrape_readiness",
                new=AsyncMock(return_value=not_ready),
            ),
            patch.object(scraping, "_create_run", new=AsyncMock()) as create_run,
        ):
            with self.assertRaisesRegex(
                scraping.ScrapePreflightError, "MongoDB unavailable"
            ):
                await scraping.start_scrape(
                    "facebook",
                    "https://facebook.com/example",
                    "Example",
                    1,
                    True,
                )

        create_run.assert_not_awaited()

    async def test_full_pipeline_rejects_unavailable_nlp_or_postgres(self):
        not_ready = ScrapeReadiness(
            source="facebook",
            ready=True,
            mongodb_ready=True,
            cookies_ready=True,
            pipeline_ready=False,
            models_ready=True,
            postgres_ready=False,
            pipeline_message="PostgreSQL is unavailable.",
            message="Scraper prerequisites are ready.",
        )
        with (
            patch.object(
                scraping,
                "get_scrape_readiness",
                new=AsyncMock(return_value=not_ready),
            ),
            patch.object(scraping, "_create_run", new=AsyncMock()) as create_run,
        ):
            with self.assertRaisesRegex(
                scraping.ScrapePreflightError, "PostgreSQL is unavailable"
            ):
                await scraping.start_scrape(
                    "facebook",
                    "https://facebook.com/example",
                    "Example",
                    1,
                    True,
                    run_full_pipeline=True,
                )

        create_run.assert_not_awaited()

    async def test_blank_worker_error_is_recorded_with_type_and_metadata(self):
        ready = ScrapeReadiness(
            source="facebook",
            ready=True,
            mongodb_ready=True,
            cookies_ready=True,
            message="Ready",
        )
        with (
            patch.object(
                scraping,
                "get_scrape_readiness",
                new=AsyncMock(return_value=ready),
            ),
            patch.object(
                scraping,
                "_create_run",
                new=AsyncMock(return_value="run-123"),
            ),
            patch.object(
                scraping,
                "_run_facebook_worker",
                side_effect=NotImplementedError(),
            ),
            patch.object(
                scraping,
                "_finish_run",
                new=AsyncMock(),
            ) as finish_run,
        ):
            with self.assertLogs(scraping.logger, level="ERROR"):
                run_id = await scraping.start_scrape(
                    "facebook",
                    "https://facebook.com/example",
                    "Example",
                    1,
                    True,
                )
                await asyncio.gather(*list(scraping._active_scrape_tasks))

        self.assertEqual(run_id, "run-123")
        finish_run.assert_awaited_once()
        args = finish_run.await_args
        self.assertEqual(args.args[0:2], ("run-123", "failed"))
        self.assertIn("Windows event loop", args.kwargs["error"])
        self.assertEqual(args.kwargs["stats"]["entity_name"], "Example")
        self.assertEqual(args.kwargs["stats"]["error_type"], "NotImplementedError")

    async def test_incomplete_request_is_recorded_as_partial_after_etl(self):
        ready = ScrapeReadiness(
            source="facebook",
            ready=True,
            mongodb_ready=True,
            cookies_ready=True,
            message="Ready",
        )
        scrape_stats = {
            "posts_requested": 3,
            "posts_discovered": 1,
            "posts_scraped": 1,
            "posts_failed": 0,
            "mongo_inserted": 0,
            "mongo_updated": 1,
        }
        with (
            patch.object(
                scraping,
                "get_scrape_readiness",
                new=AsyncMock(return_value=ready),
            ),
            patch.object(
                scraping,
                "_create_run",
                new=AsyncMock(return_value="run-partial"),
            ),
            patch.object(
                scraping,
                "_run_facebook_worker",
                return_value=scrape_stats,
            ),
            patch(
                "app.services.etl.run_full_etl",
                new=AsyncMock(return_value="etl-123"),
            ) as full_etl,
            patch.object(
                scraping,
                "_wait_for_etl_run",
                new=AsyncMock(),
            ),
            patch.object(
                scraping,
                "_finish_run",
                new=AsyncMock(),
            ) as finish_run,
        ):
            await scraping.start_scrape(
                "facebook",
                "https://facebook.com/example",
                "Example",
                3,
                True,
            )
            await asyncio.gather(*list(scraping._active_scrape_tasks))

        args = finish_run.await_args
        self.assertEqual(args.args[1], "partial")
        self.assertEqual(args.kwargs["stats"]["etl_status"], "completed")
        self.assertIn("Requested 3 posts", args.kwargs["stats"]["warning"])
        full_etl.assert_awaited_once_with(
            reprocess=False,
            threshold=0.5,
            user_id=None,
            target="contents",
        )

    async def test_facebook_worker_uses_a_subprocess_capable_loop(self):
        with patch.object(
            scraping,
            "_run_facebook_async",
            new=AsyncMock(return_value={"posts_scraped": 1}),
        ):
            result = await asyncio.to_thread(
                scraping._run_facebook_worker,
                "https://facebook.com/example",
                "Example",
                1,
                True,
            )

        self.assertEqual(result, {"posts_scraped": 1})

    async def test_scrape_only_does_not_start_etl(self):
        ready = ScrapeReadiness(
            source="foodpanda",
            ready=True,
            mongodb_ready=True,
            message="Ready",
        )
        with (
            patch.object(
                scraping,
                "get_scrape_readiness",
                new=AsyncMock(return_value=ready),
            ),
            patch.object(
                scraping,
                "_create_run",
                new=AsyncMock(return_value="run-no-etl"),
            ),
            patch.object(
                scraping,
                "_run_foodpanda_sync",
                return_value={"reviews_scraped": 4},
            ),
            patch.object(scraping, "_finish_run", new=AsyncMock()) as finish_run,
            patch(
                "app.services.etl.run_full_etl",
                new=AsyncMock(),
            ) as full_etl,
        ):
            await scraping.start_scrape(
                "foodpanda",
                "https://www.foodpanda.com.mm/restaurant/example",
                "Example",
                10,
                True,
                run_full_pipeline=False,
            )
            await asyncio.gather(*list(scraping._active_scrape_tasks))

        full_etl.assert_not_awaited()
        self.assertEqual(
            finish_run.await_args.kwargs["stats"]["etl_status"],
            "not_requested",
        )

    async def test_cooperative_cancellation_skips_pipeline(self):
        ready = ScrapeReadiness(
            source="facebook",
            ready=True,
            mongodb_ready=True,
            cookies_ready=True,
            message="Ready",
        )

        def worker(*_args):
            scraping._cancel_requests.add("run-cancel")
            return {"posts_scraped": 1, "posts_discovered": 1}

        with (
            patch.object(
                scraping,
                "get_scrape_readiness",
                new=AsyncMock(return_value=ready),
            ),
            patch.object(
                scraping,
                "_create_run",
                new=AsyncMock(return_value="run-cancel"),
            ),
            patch.object(scraping, "_run_facebook_worker", side_effect=worker),
            patch.object(scraping, "_finish_run", new=AsyncMock()) as finish_run,
        ):
            await scraping.start_scrape(
                "facebook",
                "https://facebook.com/example",
                "Example",
                1,
                True,
            )
            await asyncio.gather(*list(scraping._active_scrape_tasks))

        self.assertEqual(finish_run.await_args.args[1], "cancelled")
        self.assertTrue(
            finish_run.await_args.kwargs["stats"]["cancellation_requested"]
        )

    async def test_duplicate_active_target_becomes_conflict(self):
        class DuplicateError(Exception):
            sqlstate = "23505"

        class Transaction:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        class Connection:
            def transaction(self):
                return Transaction()

            async def fetchval(self, *_args):
                return "run-duplicate"

            async def execute(self, sql, *_args):
                if "INSERT INTO scrape_runs" in sql:
                    raise DuplicateError()
                return "OK"

        class Acquire(Transaction):
            async def __aenter__(self):
                return Connection()

        class Pool:
            def acquire(self):
                return Acquire()

        with (
            patch.object(scraping, "_ensure_table", new=AsyncMock()),
            patch.object(
                scraping,
                "get_pool",
                new=AsyncMock(return_value=Pool()),
            ),
        ):
            with self.assertRaisesRegex(
                scraping.ScrapeConflictError, "already has an active scrape"
            ):
                await scraping._create_run(
                    "scrape_facebook",
                    "00000000-0000-0000-0000-000000000001",
                    {
                        "source": "facebook",
                        "url": "https://facebook.com/example",
                        "entity_name": "Example",
                    },
                )

    def test_cron_calculation_uses_yangon_timezone(self):
        base = datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc)
        next_run = scraping.next_cron_time(
            "0 0 * * *",
            "Asia/Yangon",
            base,
        )
        self.assertEqual(
            next_run,
            datetime(2026, 8, 1, 17, 30, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
