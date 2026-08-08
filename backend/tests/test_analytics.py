from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from app.services import analytics


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""

    async def fetch(self, query, *args):
        self.query = query
        return self.rows


class _QueueConnection:
    """Returns queued results in order for mixed fetch/fetchrow calls."""

    def __init__(self, results):
        self.results = list(results)
        self.queries = []
        self.calls = []

    def _next(self, kind, query, args):
        self.queries.append(query)
        self.calls.append((kind, query, args))
        return self.results.pop(0)

    async def fetch(self, query, *args):
        return self._next("fetch", query, args)

    async def fetchrow(self, query, *args):
        return self._next("fetchrow", query, args)

    async def fetchval(self, query, *args):
        return self._next("fetchval", query, args)


class EntityAnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_entity_overview_includes_facebook_entities_without_reviews(self):
        connection = _Connection(
            [
                {
                    "entity_id": 2,
                    "entity_name": "Lotteria Myanmar",
                    "platform": "facebook",
                    "total_posts": 6,
                    "total_reactions": 5296,
                    "total_shares": 104,
                    "total_comments": 136,
                    "total_reviews": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "neutral_count": 0,
                    "positive_ratio": None,
                    "negative_ratio": None,
                    "avg_confidence": None,
                }
            ]
        )

        with patch.object(
            analytics, "get_pool", return_value=_Pool(connection)
        ):
            entities = await analytics.get_entity_sentiment_overviews()

        self.assertIn("FROM dim_entities de", connection.query)
        self.assertIn("LEFT JOIN post_stats", connection.query)
        self.assertIn("PARTITION BY entity_id, feedback_id", connection.query)
        self.assertIn("WHERE review_rank = 1", connection.query)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].entity_name, "Lotteria Myanmar")
        self.assertEqual(entities[0].total_posts, 6)
        self.assertEqual(entities[0].total_reactions, 5296)
        self.assertEqual(entities[0].total_reviews, 0)
        self.assertIsNone(entities[0].positive_ratio)

    async def test_zero_sentiment_ratio_is_not_converted_to_missing(self):
        connection = _Connection(
            [
                {
                    "entity_id": 1,
                    "entity_name": "Negative-only shop",
                    "platform": "foodpanda",
                    "total_posts": 0,
                    "total_reactions": None,
                    "total_shares": None,
                    "total_comments": None,
                    "total_reviews": 2,
                    "positive_count": 0,
                    "negative_count": 2,
                    "neutral_count": 0,
                    "positive_ratio": 0,
                    "negative_ratio": 1,
                    "avg_confidence": 0.9,
                }
            ]
        )

        with patch.object(
            analytics, "get_pool", return_value=_Pool(connection)
        ):
            entities = await analytics.get_entity_sentiment_overviews()

        self.assertEqual(entities[0].positive_ratio, 0.0)
        self.assertEqual(entities[0].negative_ratio, 1.0)


class FilteredQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_overview_applies_entity_and_days_filters(self):
        row = {
            "total_reviews": 5,
            "positive_count": 3,
            "negative_count": 1,
            "neutral_count": 1,
            "positive_ratio": 0.6,
            "negative_ratio": 0.2,
            "avg_confidence": 0.9,
        }
        connection = _QueueConnection([row])
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            overview = await analytics.get_sentiment_overview(entity_id=7, days=14)

        kind, query, args = connection.calls[0]
        self.assertEqual(kind, "fetchrow")
        self.assertIn("entity_id = $1", query)
        self.assertIn("feedback_timestamp >= CURRENT_DATE - ($2 * INTERVAL '1 day')", query)
        self.assertIn("PARTITION BY entity_id, feedback_id", query)
        self.assertIn("WHERE review_rank = 1", query)
        self.assertEqual(args, (7, 14))
        self.assertEqual(overview.total_reviews, 5)

    async def test_aspect_breakdown_filtered_queries_fact_table(self):
        connection = _QueueConnection(
            [
                [
                    {
                        "aspect_category": "fulfillment_and_speed",
                        "sentiment_label": "Negative",
                        "count": 4,
                        "avg_confidence": 0.8,
                    },
                    {
                        "aspect_category": "price_and_value",
                        "sentiment_label": None,
                        "count": 1,
                        "avg_confidence": None,
                    },
                ]
            ]
        )
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            items = await analytics.get_aspect_breakdown(entity_id=3, days=30)

        _, query, args = connection.calls[0]
        self.assertIn("FROM fact_review_absa_results", query)
        self.assertNotIn("v_aspect_breakdown", query)
        self.assertIn("sentiment_label IS NOT NULL", query)
        self.assertEqual(args, (3, 30))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].aspect, "fulfillment_and_speed")
        self.assertEqual(items[0].count, 4)

    async def test_aspect_breakdown_unfiltered_uses_view(self):
        connection = _QueueConnection(
            [
                [
                    {
                        "aspect_category": "price_and_value",
                        "sentiment_label": "Positive",
                        "count": 9,
                        "avg_confidence": 0.7,
                    }
                ]
            ]
        )
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            await analytics.get_aspect_breakdown()

        _, query, _ = connection.calls[0]
        self.assertIn("v_aspect_breakdown", query)
        self.assertIn("sentiment_label IS NOT NULL", query)


class EntityReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_reviews_are_distinct_filtered_and_cursor_paginated(self):
        created_at = datetime(2026, 8, 1, 12, 0, 0)
        row = {
            "result_id": 91,
            "feedback_id": "feedback-91",
            "review_text": "delivery was late",
            "sentiment_label": "Negative",
            "confidence_score": 0.94,
            "aspect_category": "fulfillment_and_speed",
            "created_at": created_at,
        }
        connection = _QueueConnection([[row, {**row, "result_id": 90}], 24])

        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            page = await analytics.get_entity_reviews(
                7,
                days=30,
                aspect="fulfillment_and_speed",
                limit=1,
            )

        list_call, count_call = connection.calls
        self.assertIn("PARTITION BY feedback_id", list_call[1])
        self.assertIn("aspect_category = $3", list_call[1])
        self.assertIn("COUNT(DISTINCT feedback_id)", count_call[1])
        self.assertEqual(list_call[2], (7, 30, "fulfillment_and_speed", 2))
        self.assertEqual(page.total, 24)
        self.assertEqual(page.reviews[0].feedback_id, "feedback-91")
        self.assertIsNotNone(page.next_cursor)

    async def test_focus_review_is_loaded_outside_current_page(self):
        focus_row = {
            "result_id": 12,
            "feedback_id": "clicked-review",
            "review_text": "the selected review",
            "sentiment_label": "Negative",
            "confidence_score": 0.88,
            "aspect_category": "product_quality",
            "created_at": datetime(2026, 7, 1, 8, 30, 0),
        }
        connection = _QueueConnection([[], 31, focus_row])

        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            page = await analytics.get_entity_reviews(
                4,
                days=30,
                aspect="product_quality",
                focus_feedback_id="clicked-review",
            )

        focus_call = connection.calls[2]
        self.assertEqual(focus_call[0], "fetchrow")
        self.assertIn("feedback_id = $2", focus_call[1])
        self.assertEqual(
            focus_call[2],
            (4, "clicked-review", "product_quality"),
        )
        self.assertEqual(page.focus_review.feedback_id, "clicked-review")

    async def test_invalid_review_cursor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid review cursor"):
            await analytics.get_entity_reviews(1, cursor="not-a-cursor")


class KpiTests(unittest.IsolatedAsyncioTestCase):
    def _make_connection(self):
        return _QueueConnection(
            [
                [{"d": "2026-07-30", "c": 4}, {"d": "2026-07-31", "c": 6}],
                {
                    "cur_total": 10,
                    "prev_total": 5,
                    "cur_sentiment_total": 10,
                    "prev_sentiment_total": 5,
                    "cur_pos": 6,
                    "cur_neu": 2,
                    "prev_pos": 1,
                    "prev_neu": 1,
                },
                {"cur_neg": 3, "cur_total": 8, "prev_neg": 1, "prev_total": 4},
            ]
        )

    async def test_kpis_health_hangry_and_deltas(self):
        connection = self._make_connection()
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            kpis = await analytics.get_kpis(entity_id=None, days=30)

        self.assertEqual(kpis.total_reviews, 10)
        self.assertEqual(kpis.prev_total_reviews, 5)
        self.assertEqual(kpis.volume_delta_pct, 100.0)
        self.assertEqual(len(kpis.daily_volumes), 2)
        # health = 100 * (6 + 0.5*2) / 10 = 70 ; prev = 100 * (1 + 0.5) / 5 = 30
        self.assertEqual(kpis.sentiment_health, 70.0)
        self.assertEqual(kpis.sentiment_health_delta, 40.0)
        # hangry = 3/8 = 0.375 ; prev = 1/4 = 0.25
        self.assertEqual(kpis.hangry_index, 0.375)
        self.assertEqual(kpis.hangry_delta, 0.125)

    async def test_kpis_hangry_query_scoped_to_hangry_aspects(self):
        connection = self._make_connection()
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            await analytics.get_kpis(entity_id=2, days=7)

        hangry_call = connection.calls[2]
        self.assertIn("aspect_category = ANY($2::text[])", hangry_call[1])
        self.assertEqual(
            hangry_call[2],
            (7, ["fulfillment_and_speed", "product_quality"], 2),
        )

    async def test_kpis_empty_windows_yield_nulls(self):
        connection = _QueueConnection(
            [
                [],
                {
                    "cur_total": 0,
                    "prev_total": 0,
                    "cur_sentiment_total": 0,
                    "prev_sentiment_total": 0,
                    "cur_pos": 0,
                    "cur_neu": 0,
                    "prev_pos": 0,
                    "prev_neu": 0,
                },
                {"cur_neg": 0, "cur_total": 0, "prev_neg": 0, "prev_total": 0},
            ]
        )
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            kpis = await analytics.get_kpis()

        self.assertIsNone(kpis.volume_delta_pct)
        self.assertIsNone(kpis.sentiment_health)
        self.assertIsNone(kpis.sentiment_health_delta)
        self.assertIsNone(kpis.hangry_index)
        self.assertIsNone(kpis.hangry_delta)
        self.assertEqual(kpis.daily_volumes, [])


class ReactionMixTests(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_posts_never_coerced_to_zero_ratios(self):
        row = {
            "like": 100,
            "love": 50,
            "care": 5,
            "haha": 30,
            "wow": 2,
            "sad": 1,
            "angry": 4,
            "total_posts": 20,
            "incomplete_posts": 3,
            "positivity_ratio": None,
            "negativity_ratio": None,
            "haha_ratio": None,
        }
        connection = _QueueConnection([row])
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            mix = await analytics.get_reaction_mix(entity_id=1, days=30)

        _, query, args = connection.calls[0]
        self.assertIn("like_count IS NULL", query)
        self.assertIn(
            "SUM(haha_count) FILTER (WHERE like_count IS NOT NULL",
            query,
        )
        self.assertEqual(args, (1, 30))
        self.assertEqual(mix.incomplete_posts, 3)
        self.assertIsNone(mix.positivity_ratio)
        self.assertIsNone(mix.negativity_ratio)
        self.assertIsNone(mix.haha_ratio)
        self.assertEqual(mix.like, 100)


class DriversAndFlaggedTests(unittest.IsolatedAsyncioTestCase):
    async def test_drivers_ordered_by_negative_count_with_limit(self):
        connection = _QueueConnection(
            [
                [
                    {
                        "aspect": "fulfillment_and_speed",
                        "negative_count": 12,
                        "total_count": 30,
                        "negative_share": 0.4,
                        "avg_confidence": 0.85,
                    }
                ]
            ]
        )
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            drivers = await analytics.get_top_drivers(entity_id=1, days=30, limit=8)

        _, query, args = connection.calls[0]
        self.assertIn("ORDER BY negative_count DESC", query)
        self.assertIn("aspect_category <> 'no_aspect'", query)
        self.assertEqual(args, (1, 30, 8))
        self.assertEqual(drivers[0].aspect, "fulfillment_and_speed")
        self.assertEqual(drivers[0].negative_share, 0.4)

    async def test_flagged_reviews_negative_only_with_aspect_filter(self):
        connection = _QueueConnection(
            [
                [
                    {
                        "review_text": "delivery was late",
                        "sentiment_label": "Negative",
                        "confidence_score": 0.9,
                        "aspect_category": "fulfillment_and_speed",
                        "entity_name": "OMUK",
                        "created_at": "2026-07-31 10:00:00",
                    }
                ]
            ]
        )
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            reviews = await analytics.get_flagged_reviews(
                entity_id=1, days=30, aspect="fulfillment_and_speed", limit=5
            )

        _, query, args = connection.calls[0]
        self.assertIn("r.sentiment_label = 'Negative'", query)
        self.assertIn("r.aspect_category = $3", query)
        self.assertEqual(args, (1, 30, "fulfillment_and_speed", 5))
        self.assertEqual(reviews[0].entity_name, "OMUK")
        self.assertEqual(reviews[0].sentiment_label, "Negative")


class EngagementTrendTests(unittest.IsolatedAsyncioTestCase):
    async def test_engagement_trends_groups_by_day(self):
        connection = _QueueConnection(
            [
                [
                    {
                        "d": "2026-07-31",
                        "total_reactions": 500,
                        "total_shares": 20,
                        "total_comments": 40,
                        "positivity_ratio": 0.6,
                        "negativity_ratio": 0.1,
                        "haha_ratio": 0.05,
                    }
                ]
            ]
        )
        with patch.object(analytics, "get_pool", return_value=_Pool(connection)):
            trends = await analytics.get_engagement_trends(entity_id=None, days=30)

        _, query, _ = connection.calls[0]
        self.assertIn("GROUP BY d", query)
        self.assertEqual(trends[0].total_reactions, 500)
        self.assertEqual(trends[0].positivity_ratio, 0.6)


if __name__ == "__main__":
    unittest.main()
