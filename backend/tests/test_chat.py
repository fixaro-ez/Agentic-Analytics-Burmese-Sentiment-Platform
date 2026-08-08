from __future__ import annotations

import unittest
import time
from unittest.mock import AsyncMock, patch

from app.models.chat import ChatQuery, ChatResponse
from app.services import chat


class ReadOnlySQLTests(unittest.TestCase):
    def test_allows_select_and_read_only_cte(self):
        self.assertEqual(
            chat.validate_readonly_sql("SELECT * FROM v_entity_sentiment_overview;"),
            "SELECT * FROM v_entity_sentiment_overview",
        )
        self.assertEqual(
            chat.validate_readonly_sql(
                "WITH totals AS (SELECT count(*) AS n FROM dim_entities) "
                "SELECT n FROM totals"
            ),
            (
                "WITH totals AS (SELECT count(*) AS n FROM dim_entities) "
                "SELECT n FROM totals"
            ),
        )

    def test_rejects_writes_multi_statement_comments_and_row_locks(self):
        unsafe_queries = [
            "DELETE FROM dim_entities",
            "WITH changed AS (UPDATE dim_entities SET entity_name='x' RETURNING *) "
            "SELECT * FROM changed",
            "SELECT 1; DROP TABLE dim_entities",
            "SELECT * INTO copied_entities FROM dim_entities",
            "SELECT * FROM dim_entities FOR UPDATE",
            "/* hidden */ UPDATE dim_entities SET entity_name='x'",
            "SELECT pg_read_file('/etc/passwd')",
        ]
        for sql in unsafe_queries:
            with self.subTest(sql=sql), self.assertRaises(chat.UnsafeSQL):
                chat.validate_readonly_sql(sql)

    def test_keywords_inside_string_literals_do_not_become_statements(self):
        sql = "SELECT 'drop table dim_entities' AS harmless"
        self.assertEqual(chat.validate_readonly_sql(sql), sql)

    def test_branch_scope_rejects_unfiltered_generated_sql(self):
        question = "what branch of kfc has the most positive reviews"
        with self.assertRaises(chat.QueryScopeMismatch):
            chat.validate_question_scope(
                question,
                "SELECT * FROM v_entity_sentiment_overview",
            )

    def test_branch_scope_accepts_brand_bridge_query(self):
        chat.validate_question_scope(
            "what branch of kfc has the most positive reviews",
            "SELECT overview.* FROM v_entity_sentiment_overview overview "
            "JOIN bridge_brand_foodpanda_shops bridge "
            "ON bridge.entity_id = overview.entity_id "
            "JOIN dim_brands brand ON brand.brand_id = bridge.brand_id "
            "WHERE LOWER(brand.brand_name) = 'kfc'",
        )


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        chat._CONVERSATIONS.clear()

    async def _events(self, generator):
        return [event async for event in generator]

    async def test_stream_emits_layers_and_done(self):
        response = ChatResponse(
            question="show trends",
            explanation="Daily trend explanation",
            results=[{"date": "2026-07-31", "negative_count": 2}],
            sql="SELECT 1",
        )
        with patch.object(chat, "answer_question", new=AsyncMock(return_value=response)):
            events = await self._events(
                chat.stream_answer_events(
                    ChatQuery(question="show trends"), "user-1"
                )
            )

        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[:2], ["meta", "status"])
        self.assertIn("explanation_delta", event_types)
        self.assertIn("response", event_types)
        self.assertEqual(event_types[-1], "done")

    async def test_stream_turns_backend_failure_into_error_event(self):
        with patch.object(
            chat,
            "answer_question",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ):
            events = await self._events(
                chat.stream_answer_events(
                    ChatQuery(question="show trends"), "user-1"
                )
            )

        self.assertEqual(events[-2]["type"], "error")
        self.assertIn("database unavailable", events[-2]["error"])
        self.assertEqual(events[-1], {"type": "done"})

    async def test_stream_surfaces_query_planner_error_instead_of_empty_result(self):
        response = ChatResponse(
            question="what is the current schema",
            error="The AI query planner is unavailable",
        )
        with patch.object(chat, "answer_question", new=AsyncMock(return_value=response)):
            events = await self._events(
                chat.stream_answer_events(
                    ChatQuery(question="what is the current schema"), "user-1"
                )
            )

        self.assertEqual(events[-2], {
            "type": "error",
            "error": "The AI query planner is unavailable",
        })
        self.assertNotIn("response", [event["type"] for event in events])
        self.assertEqual(events[-1], {"type": "done"})


class KeywordRouteTests(unittest.TestCase):
    def test_matches_known_patterns(self):
        result = chat._keyword_route("show me the aspect breakdown", "en")
        self.assertIsNotNone(result)
        sql, _, chart = result
        self.assertIn("v_aspect_breakdown", sql)
        self.assertEqual(chart.type, "bar")

        result = chat._keyword_route("what is the trend over time", "en")
        self.assertIsNotNone(result)
        self.assertIn("v_sentiment_daily_trends", result[0])

        result = chat._keyword_route("which entities have the most negative reviews", "en")
        self.assertIsNotNone(result)
        self.assertIn("negative_ratio", result[0])

        result = chat._keyword_route("show me the best positive entities", "en")
        self.assertIsNotNone(result)
        self.assertIn("positive_ratio", result[0])

        result = chat._keyword_route(
            "what branch of kfc has the most positive reviews", "en"
        )
        self.assertIsNotNone(result)
        self.assertIn("bridge_brand_foodpanda_shops", result[0])
        self.assertIn("LOWER('kfc')", result[0])
        self.assertIn("KFC branches", result[1])

        result = chat._keyword_route("how many reviews are there", "en")
        self.assertIsNotNone(result)
        self.assertIn("COUNT(DISTINCT", result[0])

        result = chat._keyword_route("compare entities", "en")
        self.assertIsNotNone(result)
        self.assertIn("v_entity_sentiment_overview", result[0])

        result = chat._keyword_route("show Facebook engagement", "en")
        self.assertIsNotNone(result)
        self.assertIn("v_facebook_engagement", result[0])

        result = chat._keyword_route("how do you know the db schema", "en")
        self.assertIsNotNone(result)
        self.assertIn("information_schema.columns", result[0])

    def test_returns_none_for_unmatched(self):
        self.assertIsNone(chat._keyword_route("hello", "en"))
        self.assertIsNone(chat._keyword_route("show me raw reviews for KFC", "en"))

    def test_translate_for_burmese(self):
        result = chat._keyword_route("show aspect data", "my")
        self.assertIsNotNone(result)
        self.assertNotEqual(result[1], "Here are the most frequently detected aspect and sentiment pairs.")

    def test_provider_errors_are_safe_for_display(self):
        error = RuntimeError(
            "400 INVALID_ARGUMENT: Manually set deadline 6s is too short"
        )
        public = chat._public_llm_error(error)
        self.assertIn("timed out", public)
        self.assertNotIn("INVALID_ARGUMENT", public)

    def test_branch_brand_filter_escapes_quotes(self):
        result = chat._keyword_route(
            "what branch of kfc' OR 1=1 -- has the most positive reviews", "en"
        )
        self.assertIsNotNone(result)
        self.assertIn("LOWER('kfc'' OR 1=1')", result[0])
        chat.validate_readonly_sql(result[0])


class QueryDataFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        chat._CONVERSATIONS.clear()
        chat._QUERY_CACHE.clear()
        chat._PLAN_CACHE.clear()

    async def test_llm_planner_used_even_when_template_matches(self):
        planned = ("SELECT 1 AS planned", "generated", None)
        with (
            patch.object(chat, "_llm_query_plan", new=AsyncMock(return_value=planned)) as planner,
            patch.object(chat, "_execute_readonly", new=AsyncMock(return_value=[])),
        ):
            response = await chat.query_data("show aspect breakdown")
        planner.assert_awaited_once()
        self.assertEqual(response.sql, "SELECT 1 AS planned")
        self.assertIsNone(response.error)

    async def test_error_when_no_api_key_and_no_keyword_match(self):
        with (
            patch.object(chat.settings, "GOOGLE_API_KEY", ""),
            patch.object(chat.settings, "CHAT_TEMPLATE_FALLBACK", False),
        ):
            response = await chat.query_data("how many brands are there")
        self.assertIsNone(response.sql)
        self.assertIsNotNone(response.error)
        self.assertIn("GOOGLE_API_KEY", response.error)

    async def test_template_route_is_only_explicit_fallback(self):
        with (
            patch.object(chat.settings, "CHAT_TEMPLATE_FALLBACK", True),
            patch.object(chat, "_llm_query_plan", new=AsyncMock(return_value=None)),
            patch.object(chat, "_execute_readonly", new=AsyncMock(return_value=[])),
        ):
            response = await chat.query_data("how many brands are there")
        self.assertIn("dim_brands", response.sql)

    def test_text_to_sql_prompt_requires_brand_branch_scope(self):
        prompt = chat._build_system_prompt()
        self.assertIn("bridge_brand_foodpanda_shops", prompt)
        self.assertIn("Do not rank unrelated entities", prompt)
        self.assertIn("Never silently drop a requested filter", prompt)

    async def test_llm_fallback_returns_sql_on_success(self):
        fake_result = ("SELECT count(*) FROM dim_entities", "results", None)
        with (
            patch.object(chat.settings, "GOOGLE_API_KEY", "fake-key"),
            patch.object(chat, "_llm_query_plan", new=AsyncMock(return_value=fake_result)),
            patch.object(chat, "_execute_readonly", new=AsyncMock(return_value=[{"count": 42}])),
        ):
            response = await chat.query_data("find the median review confidence")
        self.assertEqual(response.sql, "SELECT count(*) FROM dim_entities")
        self.assertEqual(response.results, [{"count": 42}])
        self.assertIsNone(response.error)

    async def test_readonly_query_uses_fresh_cache_entry(self):
        chat._QUERY_CACHE["SELECT 1 AS value"] = (
            time.monotonic() + 10,
            ({"value": 1},),
        )
        with patch.object(chat, "get_pool", new=AsyncMock()) as get_pool:
            rows = await chat._execute_readonly("SELECT 1 AS value")
        self.assertEqual(rows, [{"value": 1}])
        get_pool.assert_not_awaited()

    async def test_llm_plan_uses_fresh_cache_entry(self):
        key = ("find the median review confidence", "en")
        cached = ("SELECT 1", "cached result", None)
        chat._PLAN_CACHE[key] = (time.monotonic() + 10, cached)
        with patch.object(chat.settings, "GOOGLE_API_KEY", "fake-key"):
            result = await chat._llm_query_plan(*key)
        self.assertEqual(result, cached)


if __name__ == "__main__":
    unittest.main()
