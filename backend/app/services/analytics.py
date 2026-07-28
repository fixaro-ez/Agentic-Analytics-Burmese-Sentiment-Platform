from __future__ import annotations

from ..database import get_pool
from ..models.analytics import (
    AspectBreakdown,
    EntitySentimentOverview,
    FacebookEngagement,
    SentimentOverview,
    SentimentTrendPoint,
)


async def get_sentiment_overview() -> SentimentOverview:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT "
            "  COUNT(*)::int AS total_reviews, "
            "  COUNT(CASE WHEN sentiment_label = 'Positive' THEN 1 END)::int AS positive_count, "
            "  COUNT(CASE WHEN sentiment_label = 'Negative' THEN 1 END)::int AS negative_count, "
            "  COUNT(CASE WHEN sentiment_label = 'Neutral' THEN 1 END)::int AS neutral_count, "
            "  ROUND(COUNT(CASE WHEN sentiment_label = 'Positive' THEN 1 END)::NUMERIC / NULLIF(COUNT(*), 0), 4) AS positive_ratio, "
            "  ROUND(COUNT(CASE WHEN sentiment_label = 'Negative' THEN 1 END)::NUMERIC / NULLIF(COUNT(*), 0), 4) AS negative_ratio, "
            "  ROUND(AVG(confidence_score), 4) AS avg_confidence "
            "FROM fact_review_absa_results"
        )
    return SentimentOverview(
        total_reviews=row["total_reviews"] or 0,
        positive_count=row["positive_count"] or 0,
        negative_count=row["negative_count"] or 0,
        neutral_count=row["neutral_count"] or 0,
        positive_ratio=float(row["positive_ratio"] or 0),
        negative_ratio=float(row["negative_ratio"] or 0),
        avg_confidence=float(row["avg_confidence"]) if row["avg_confidence"] else None,
    )


async def get_entity_sentiment_overviews() -> list[EntitySentimentOverview]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM v_entity_sentiment_overview ORDER BY total_reviews DESC"
        )
    return [
        EntitySentimentOverview(
            entity_id=r["entity_id"],
            entity_name=r["entity_name"],
            platform=r["platform"],
            total_reviews=r["total_reviews"] or 0,
            positive_count=r["positive_count"] or 0,
            negative_count=r["negative_count"] or 0,
            neutral_count=r["neutral_count"] or 0,
            positive_ratio=float(r["positive_ratio"]) if r["positive_ratio"] else None,
            negative_ratio=float(r["negative_ratio"]) if r["negative_ratio"] else None,
            avg_confidence=float(r["avg_confidence"]) if r["avg_confidence"] else None,
        )
        for r in rows
    ]


async def get_aspect_breakdown() -> list[AspectBreakdown]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM v_aspect_breakdown ORDER BY aspect, count DESC"
        )
    return [
        AspectBreakdown(
            aspect=r["aspect_category"],
            sentiment=r["sentiment_label"],
            count=r["count"],
            avg_confidence=float(r["avg_confidence"]) if r["avg_confidence"] else 0,
        )
        for r in rows
    ]


async def get_sentiment_trends(
    entity_id: int | None = None, days: int = 30
) -> list[SentimentTrendPoint]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if entity_id is not None:
            rows = await conn.fetch(
                "SELECT * FROM v_sentiment_daily_trends "
                "WHERE entity_id = $1 AND feedback_date >= CURRENT_DATE - $2::INTERVAL "
                "ORDER BY feedback_date",
                entity_id,
                f"{days} days",
            )
        else:
            rows = await conn.fetch(
                "SELECT feedback_date, NULL::int AS entity_id, "
                "  'all' AS entity_name, 'all' AS platform, "
                "  SUM(total_reviews)::int AS total_reviews, "
                "  SUM(positive_count)::int AS positive_count, "
                "  SUM(negative_count)::int AS negative_count, "
                "  SUM(neutral_count)::int AS neutral_count, "
                "  ROUND(SUM(positive_count)::NUMERIC / NULLIF(SUM(total_reviews), 0), 4) AS positive_ratio "
                "FROM v_sentiment_daily_trends "
                "WHERE feedback_date >= CURRENT_DATE - $1::INTERVAL "
                "GROUP BY feedback_date ORDER BY feedback_date",
                f"{days} days",
            )
    return [
        SentimentTrendPoint(
            date=str(r["feedback_date"]),
            entity_id=r["entity_id"],
            entity_name=r["entity_name"],
            total_reviews=r["total_reviews"],
            positive_count=r["positive_count"],
            negative_count=r["negative_count"],
            neutral_count=r["neutral_count"],
            positive_ratio=float(r["positive_ratio"] or 0),
        )
        for r in rows
    ]


async def get_facebook_engagement() -> list[FacebookEngagement]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM v_facebook_engagement ORDER BY total_reactions DESC NULLS LAST"
        )
    return [
        FacebookEngagement(
            entity_id=r["entity_id"],
            entity_name=r["entity_name"],
            total_posts=r["total_posts"] or 0,
            total_reactions=r["total_reactions"],
            total_shares=r["total_shares"],
            total_comments=r["total_comments"],
            avg_positivity_ratio=float(r["avg_positivity_ratio"]) if r["avg_positivity_ratio"] else None,
            avg_negativity_ratio=float(r["avg_negativity_ratio"]) if r["avg_negativity_ratio"] else None,
        )
        for r in rows
    ]
