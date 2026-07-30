from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..database import get_pool
from ..models.chat import ChatResponse


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _serialize_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in dict(row).items()}
        for row in rows
    ]


async def query_data(question: str) -> ChatResponse:
    """Answer common analytics questions with approved read-only queries."""
    normalized = " ".join(question.lower().split())

    if "aspect" in normalized:
        sql = (
            "SELECT aspect_category AS aspect, sentiment_label AS sentiment, "
            "count, avg_confidence FROM v_aspect_breakdown "
            "ORDER BY count DESC LIMIT 20"
        )
        explanation = (
            "Here are the most frequently detected aspect and sentiment pairs."
        )
    elif "trend" in normalized or "over time" in normalized:
        sql = (
            "SELECT feedback_date AS date, SUM(total_reviews)::int AS total_reviews, "
            "SUM(positive_count)::int AS positive_count, "
            "SUM(negative_count)::int AS negative_count, "
            "SUM(neutral_count)::int AS neutral_count "
            "FROM v_sentiment_daily_trends "
            "WHERE feedback_date >= CURRENT_DATE - INTERVAL '30 days' "
            "GROUP BY feedback_date ORDER BY feedback_date LIMIT 100"
        )
        explanation = "This is the daily sentiment trend for the last 30 days."
    elif "negative" in normalized and (
        "most" in normalized or "highest" in normalized or "worst" in normalized
    ):
        sql = (
            "SELECT entity_name, platform, total_reviews, negative_count, "
            "negative_ratio FROM v_entity_sentiment_overview "
            "ORDER BY negative_ratio DESC NULLS LAST, total_reviews DESC LIMIT 10"
        )
        explanation = (
            "Entities are ranked by negative-review ratio, with review volume "
            "used as the tie-breaker."
        )
    elif "positive" in normalized and (
        "most" in normalized or "highest" in normalized or "best" in normalized
    ):
        sql = (
            "SELECT entity_name, platform, total_reviews, positive_count, "
            "positive_ratio FROM v_entity_sentiment_overview "
            "ORDER BY positive_ratio DESC NULLS LAST, total_reviews DESC LIMIT 10"
        )
        explanation = (
            "Entities are ranked by positive-review ratio, with review volume "
            "used as the tie-breaker."
        )
    else:
        sql = (
            "SELECT entity_name, platform, total_reviews, positive_ratio, "
            "negative_ratio, avg_confidence FROM v_entity_sentiment_overview "
            "ORDER BY total_reviews DESC LIMIT 20"
        )
        explanation = (
            "Here is the current sentiment overview by entity. Try asking for "
            "the most positive or negative entities, trends, or aspect results."
        )

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(sql, timeout=30)

    return ChatResponse(
        question=question,
        sql=sql,
        results=_serialize_rows(rows),
        explanation=explanation,
    )
