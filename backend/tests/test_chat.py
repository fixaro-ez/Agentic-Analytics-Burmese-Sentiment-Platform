from __future__ import annotations

import unittest
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

    def test_returns_none_for_unmatched(self):
        self.assertIsNone(chat._keyword_route("how many reviews are there", "en"))
        self.assertIsNone(chat._keyword_route("hello", "en"))
        self.assertIsNone(chat._keyword_route("show me raw reviews for KFC", "en"))

    def test_translate_for_burmese(self):
        result = chat._keyword_route("show aspect data", "my")
        self.assertIsNotNone(result)
        self.assertNotEqual(result[1], "Here are the most frequently detected aspect and sentiment pairs.")


class QueryDataFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        chat._CONVERSATIONS.clear()

    async def test_keyword_route_used_when_matched(self):
        with patch.object(chat, "_execute_readonly", new=AsyncMock(return_value=[])):
            response = await chat.query_data("show aspect breakdown")
        self.assertIn("v_aspect_breakdown", response.sql)
        self.assertIsNone(response.error)

    async def test_error_when_no_api_key_and_no_keyword_match(self):
        with patch.object(chat.settings, "GOOGLE_API_KEY", ""):
            response = await chat.query_data("how many total reviews exist")
        self.assertIsNone(response.sql)
        self.assertIsNotNone(response.error)
        self.assertIn("GOOGLE_API_KEY", response.error)

    async def test_llm_fallback_returns_sql_on_success(self):
        fake_result = ("SELECT count(*) FROM dim_entities", "results", None)
        with (
            patch.object(chat.settings, "GOOGLE_API_KEY", "fake-key"),
            patch.object(chat, "_llm_query_plan", new=AsyncMock(return_value=fake_result)),
            patch.object(chat, "_execute_readonly", new=AsyncMock(return_value=[{"count": 42}])),
        ):
            response = await chat.query_data("count all entities in the database")
        self.assertEqual(response.sql, "SELECT count(*) FROM dim_entities")
        self.assertEqual(response.results, [{"count": 42}])
        self.assertIsNone(response.error)


if __name__ == "__main__":
    unittest.main()
