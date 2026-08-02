import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from burmese_absa.scraping import (
    _count_info,
    _canonical_post_permalink,
    _href_belongs_to_facebook_page,
    _is_post_permalink,
    _parse_timestamp_text,
    _post_candidate_belongs_to_page,
    _parse_reaction_payload,
    _permalink_score,
    _reaction_toolbar,
    _reaction_type,
    _summary_total,
    compute_reaction_metrics,
    migrate_facebook_schema,
)
from burmese_absa.scraping.facebook import (
    _aggregate_metric,
    _detect_interruption,
    _engagement_action_counts,
    _facebook_interruption_message,
    _metric_count_info,
    _partial_reaction_payload,
    _post_surface_score,
    _reaction_count_info,
    _totals_compatible,
    _write_facebook_report,
)


class ReactionMetricTests(unittest.TestCase):
    def test_complete_grouping_and_ratios(self):
        raw = {
            "like": 68,
            "love": 16,
            "care": 1,
            "haha": 1,
            "wow": 0,
            "sad": 0,
            "angry": 0,
            "total": 86,
        }
        self.assertEqual(
            compute_reaction_metrics(raw),
            {
                "passive_engagement": 68,
                "positive_affinity": 17,
                "negative_risk": 0,
                "expressive_virality": 1,
                "positivity_ratio": 0.197674,
                "negativity_ratio": 0.0,
                "haha_ratio": 0.011628,
            },
        )

    def test_zero_total_has_zero_ratios(self):
        raw = {key: 0 for key in ("like", "love", "care", "haha", "wow", "sad", "angry")}
        raw["total"] = 0
        metrics = compute_reaction_metrics(raw)
        self.assertEqual(metrics["positivity_ratio"], 0.0)
        self.assertEqual(metrics["negativity_ratio"], 0.0)
        self.assertEqual(metrics["haha_ratio"], 0.0)

    def test_partial_values_null_only_affected_metrics(self):
        raw = {
            "like": 68,
            "love": 17,
            "care": None,
            "haha": None,
            "wow": None,
            "sad": None,
            "angry": None,
            "total": 86,
        }
        metrics = compute_reaction_metrics(raw)
        self.assertEqual(metrics["passive_engagement"], 68)
        self.assertIsNone(metrics["positive_affinity"])
        self.assertIsNone(metrics["negative_risk"])
        self.assertIsNone(metrics["expressive_virality"])
        self.assertIsNone(metrics["positivity_ratio"])
        self.assertIsNone(metrics["haha_ratio"])

    def test_complete_counts_can_calculate_missing_total(self):
        raw = {
            "like": 2,
            "love": 1,
            "care": 0,
            "haha": 1,
            "wow": 0,
            "sad": 0,
            "angry": 0,
        }
        metrics = compute_reaction_metrics(raw)
        self.assertEqual(metrics["positivity_ratio"], 0.25)
        self.assertEqual(metrics["haha_ratio"], 0.25)

    def test_rejects_invalid_and_inconsistent_counts(self):
        base = {key: 0 for key in ("like", "love", "care", "haha", "wow", "sad", "angry")}
        with self.assertRaises(ValueError):
            compute_reaction_metrics({**base, "like": -1})
        with self.assertRaises(ValueError):
            compute_reaction_metrics({**base, "like": True})
        with self.assertRaises(ValueError):
            compute_reaction_metrics({**base, "like": 1, "total": 2})


class ReactionParsingTests(unittest.TestCase):
    def test_page_ownership_rejects_foreign_posts(self):
        page = "https://www.facebook.com/LotteriaMyanmar"
        self.assertTrue(
            _href_belongs_to_facebook_page(
                "https://www.facebook.com/LotteriaMyanmar/posts/pfbid123", page
            )
        )
        self.assertFalse(
            _href_belongs_to_facebook_page(
                "https://www.facebook.com/SomeOtherPage/posts/pfbid456", page
            )
        )
        self.assertTrue(
            _post_candidate_belongs_to_page(
                "https://www.facebook.com/reel/3949234062045009/", page
            )
        )

    def test_relative_post_timestamp_words(self):
        now = datetime(2026, 7, 23, 12, 0, 0)
        self.assertEqual(
            _parse_timestamp_text("a day ago", now), now - timedelta(days=1)
        )
        self.assertEqual(
            _parse_timestamp_text("2 hours ago", now), now - timedelta(hours=2)
        )
        self.assertEqual(
            _parse_timestamp_text('- link "2 days ago":', now),
            now - timedelta(days=2),
        )
        self.assertEqual(
            _parse_timestamp_text('- link "a day ago":', now),
            now - timedelta(days=1),
        )

    def test_absolute_facebook_tooltip_timestamp(self):
        myanmar_timezone = timezone(timedelta(hours=6, minutes=30))
        now = datetime(2026, 7, 23, 12, 0, tzinfo=myanmar_timezone)
        parsed = _parse_timestamp_text(
            "Wednesday, July 22, 2026 at 8:07 PM", now
        )
        self.assertEqual(
            parsed,
            datetime(2026, 7, 22, 20, 7, tzinfo=myanmar_timezone),
        )

    def test_permalink_filter_rejects_generic_navigation_routes(self):
        self.assertFalse(_is_post_permalink("https://www.facebook.com/photo/"))
        self.assertFalse(_is_post_permalink("https://www.facebook.com/reel/"))
        self.assertTrue(
            _is_post_permalink(
                "https://www.facebook.com/Page/posts/pfbid123456789"
            )
        )

    def test_comment_permalink_is_canonicalized_to_parent_post(self):
        href = (
            "https://www.facebook.com/Page/posts/pfbid123456789"
            "?comment_id=55&__cft__[0]=token"
        )
        canonical = _canonical_post_permalink(href, "https://www.facebook.com/Page")
        self.assertEqual(
            canonical,
            "https://www.facebook.com/Page/posts/pfbid123456789",
        )
        self.assertGreater(
            _permalink_score(href),
            _permalink_score("https://www.facebook.com/photo/?fbid=123"),
        )

    def test_exact_compact_and_burmese_counts(self):
        self.assertEqual(_count_info("1,234 reactions"), (1234, True))
        self.assertEqual(_count_info("1.2K reactions"), (1200, False))
        self.assertEqual(_count_info("၈၆ reactions"), (86, True))

    def test_english_and_burmese_reaction_labels(self):
        self.assertEqual(_reaction_type("Like: 68 people"), "like")
        self.assertEqual(_reaction_type("ဝမ်းနည်း ၃"), "sad")
        self.assertEqual(_reaction_type("ဒေါသထွက် ၂"), "angry")

    def test_summary_and_toolbar(self):
        total, exact, label = _summary_total(["All reactions: 86"])
        self.assertEqual((total, exact), (86, True))
        self.assertIn("All reactions", label)
        counts, toolbar_exact = _reaction_toolbar(
            ["Like: 68 people", "Love: 17 people", "4 shares"]
        )
        self.assertEqual(counts, {"like": 68, "love": 17})
        self.assertTrue(toolbar_exact)

    def test_metric_parser_keeps_comment_and_share_numbers_separate(self):
        label = "2.7K reactions 128 comments 201 shares"
        self.assertEqual(_metric_count_info(label, "comments"), (128, True))
        self.assertEqual(_metric_count_info(label, "shares"), (201, True))
        self.assertEqual(_aggregate_metric([label], "comments"), 128)
        self.assertEqual(_aggregate_metric([label], "shares"), 201)

    def test_reaction_parser_ignores_numbers_not_attached_to_reaction(self):
        label = "Like Comment 128 Share 201"
        self.assertEqual(_reaction_count_info(label, "like"), (None, False))
        counts, _ = _reaction_toolbar([label])
        self.assertEqual(counts, {})

    def test_compact_total_rejects_cross_contaminated_category_sum(self):
        self.assertTrue(_totals_compatible(2715, 2700, False))
        self.assertFalse(_totals_compatible(3330, 2700, False))
        raw, contaminated = _partial_reaction_payload(
            {"like": 2600, "love": 730}, 2700, False
        )
        self.assertTrue(contaminated)
        self.assertEqual(raw["total"], 2700)
        self.assertTrue(all(raw[key] is None for key in (
            "like", "love", "care", "haha", "wow", "sad", "angry"
        )))

    def test_summary_ignores_smaller_background_post_total(self):
        total, exact, _ = _summary_total(
            ["All reactions: 1", "All reactions: 87", "2 reactions; see who reacted"]
        )
        self.assertEqual((total, exact), (87, True))

    def test_dialog_payload_parses_all_reactions(self):
        payload = {
            "items": [
                {"aria": "Like 10", "title": "", "text": "", "alts": "Like"},
                {"aria": "Love 3", "title": "", "text": "", "alts": "Love"},
                {"aria": "Care 2", "title": "", "text": "", "alts": "Care"},
                {"aria": "Haha 1", "title": "", "text": "", "alts": "Haha"},
                {"aria": "Wow 1", "title": "", "text": "", "alts": "Wow"},
                {"aria": "Sad 1", "title": "", "text": "", "alts": "Sad"},
                {"aria": "Angry 1", "title": "", "text": "", "alts": "Angry"},
            ]
        }
        counts, exact = _parse_reaction_payload(payload)
        self.assertEqual(sum(counts.values()), 19)
        self.assertEqual(set(counts), {"like", "love", "care", "haha", "wow", "sad", "angry"})
        self.assertTrue(exact)


class PostSurfaceCorrelationTests(unittest.IsolatedAsyncioTestCase):
    async def test_reel_action_row_extracts_all_three_meta_counts(self):
        surface = MagicMock()
        surface.evaluate = AsyncMock(
            return_value=[
                {"kind": "reactions", "text": "2.7K"},
                {"kind": "comments", "text": "128"},
                {"kind": "shares", "text": "201"},
            ]
        )

        counts = await _engagement_action_counts(surface)

        self.assertEqual(counts["reactions"], (2700, False, "2.7K"))
        self.assertEqual(counts["comments"], (128, True, "128"))
        self.assertEqual(counts["shares"], (201, True, "201"))

    async def test_hidden_exact_post_is_accepted_when_page_identity_matches(self):
        platform_id = "pfbid123"
        handle = MagicMock()
        handle.is_visible = AsyncMock(return_value=False)
        handle.evaluate = AsyncMock(
            return_value={
                "role": "dialog",
                "tag": "DIV",
                "text": "Lotteria Myanmar post content",
                "hrefs": [f"https://facebook.com/posts/{platform_id}"],
                "messages": 1,
                "actions": ["Actions for this post by Lotteria Myanmar"],
            }
        )
        candidate = MagicMock()
        candidate.element_handle = AsyncMock(return_value=handle)

        score = await _post_surface_score(
            candidate, platform_id, "lotteriamyanmar"
        )

        self.assertGreaterEqual(score, 100)

    async def test_hidden_background_post_is_rejected_when_identity_differs(self):
        platform_id = "pfbid123"
        handle = MagicMock()
        handle.is_visible = AsyncMock(return_value=False)
        handle.evaluate = AsyncMock(
            return_value={
                "role": "dialog",
                "tag": "DIV",
                "text": "Unrelated post",
                "hrefs": [f"https://facebook.com/posts/{platform_id}"],
                "messages": 1,
                "actions": ["Actions for this post by nixCraft"],
            }
        )
        candidate = MagicMock()
        candidate.element_handle = AsyncMock(return_value=handle)

        score = await _post_surface_score(
            candidate, platform_id, "lotteriamyanmar"
        )

        self.assertEqual(score, -1)


class FacebookInterruptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_content_unavailable_page_is_detected(self):
        body = MagicMock()
        body.inner_text = AsyncMock(
            return_value="This content isn't available at the moment"
        )
        page = MagicMock()
        page.url = "https://www.facebook.com/Lotteria%20Myanmar"
        page.locator.return_value = body

        reason = await _detect_interruption(page)

        self.assertEqual(reason, "unavailable")

    def test_unavailable_message_identifies_url_problem(self):
        message = _facebook_interruption_message(
            "unavailable",
            "https://www.facebook.com/Lotteria Myanmar",
        )

        self.assertIn("page is unavailable", message)
        self.assertIn("do not contain spaces", message)
        self.assertIn("LotteriaMyanmar", message)


class FacebookReportTests(unittest.TestCase):
    def test_current_failure_atomically_replaces_stale_success_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "facebook_run_report.json"
            report_path.write_text(
                json.dumps({"status": "completed", "saved": 3}),
                encoding="utf-8",
            )

            _write_facebook_report(
                str(report_path),
                {
                    "status": "failed",
                    "saved": 0,
                    "errors": ["Page unavailable"],
                },
            )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["saved"], 0)
            self.assertEqual(report["errors"], ["Page unavailable"])
            self.assertFalse(report_path.with_suffix(".json.tmp").exists())


class MigrationDryRunTests(unittest.TestCase):
    def test_migration_is_non_destructive_without_confirmation(self):
        class Collection:
            def __init__(self, documents=None, count=0):
                self.documents = documents or []
                self.count = count
                self.delete_called = False

            def find(self, _query):
                return list(self.documents)

            def count_documents(self, _query):
                return self.count

            def delete_many(self, _query):
                self.delete_called = True

        class Database:
            contents = Collection([{"_id": "fb_post_one"}])
            feedbacks = Collection(count=3)

        database = Database()
        report = migrate_facebook_schema(database, confirm_delete=False)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["facebook_contents"], 1)
        self.assertEqual(report["facebook_feedbacks_to_delete"], 3)
        self.assertFalse(database.feedbacks.delete_called)


if __name__ == "__main__":
    unittest.main()
