from __future__ import annotations

import base64
import json
from datetime import datetime

from ..database import get_pool
from ..models.analytics import (
    AspectBreakdown,
    DailyVolume,
    DriverItem,
    EngagementTrendPoint,
    EntityAspectItem,
    EntityReview,
    EntityReviewPageResponse,
    EntitySentimentOverview,
    FacebookEngagement,
    FlaggedReview,
    KpiResponse,
    ReactionMix,
    SentimentOverview,
    SentimentTrendPoint,
)

# Aspects that feed the Hangry Index: food-delivery "hangry" complaints
# are fundamentally about speed/fulfillment and product quality.
HANGRY_ASPECTS = ("fulfillment_and_speed", "product_or_service_quality")


def _review_filters(
    entity_id: int | None, days: int | None, alias: str = ""
) -> tuple[str, list]:
    """Build a WHERE clause (without the WHERE keyword) + params for
    fact_review_absa_results. `alias` is a table alias prefix like 'r.'."""
    clauses: list[str] = []
    params: list = []
    if entity_id is not None:
        params.append(entity_id)
        clauses.append(f"{alias}entity_id = ${len(params)}")
    if days is not None:
        params.append(days)
        clauses.append(
            f"{alias}feedback_timestamp >= CURRENT_DATE - (${len(params)} * INTERVAL '1 day')"
        )
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _post_filters(entity_id: int | None, days: int | None) -> tuple[str, list]:
    """Same as _review_filters but for fact_social_posts (post_timestamp)."""
    clauses: list[str] = []
    params: list = []
    if entity_id is not None:
        params.append(entity_id)
        clauses.append(f"entity_id = ${len(params)}")
    if days is not None:
        params.append(days)
        clauses.append(
            f"post_timestamp >= CURRENT_DATE - (${len(params)} * INTERVAL '1 day')"
        )
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


async def get_sentiment_overview(
    entity_id: int | None = None, days: int | None = None
) -> SentimentOverview:
    where, params = _review_filters(entity_id, days)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "WITH ranked_reviews AS ("
            "  SELECT feedback_id, sentiment_label, confidence_score, "
            "    ROW_NUMBER() OVER ("
            "      PARTITION BY entity_id, feedback_id "
            "      ORDER BY (sentiment_label IS NOT NULL) DESC, "
            "        confidence_score DESC NULLS LAST, result_id DESC"
            "    ) AS review_rank "
            f"  FROM fact_review_absa_results{where}"
            ") SELECT "
            "  COUNT(*)::int AS total_reviews, "
            "  COUNT(CASE WHEN sentiment_label = 'Positive' THEN 1 END)::int AS positive_count, "
            "  COUNT(CASE WHEN sentiment_label = 'Negative' THEN 1 END)::int AS negative_count, "
            "  COUNT(CASE WHEN sentiment_label = 'Neutral' THEN 1 END)::int AS neutral_count, "
            "  ROUND(COUNT(CASE WHEN sentiment_label = 'Positive' THEN 1 END)::NUMERIC "
            "    / NULLIF(COUNT(*) FILTER (WHERE sentiment_label IS NOT NULL), 0), 4) AS positive_ratio, "
            "  ROUND(COUNT(CASE WHEN sentiment_label = 'Negative' THEN 1 END)::NUMERIC "
            "    / NULLIF(COUNT(*) FILTER (WHERE sentiment_label IS NOT NULL), 0), 4) AS negative_ratio, "
            "  ROUND(AVG(confidence_score) FILTER (WHERE sentiment_label IS NOT NULL), 4) AS avg_confidence "
            "FROM ranked_reviews WHERE review_rank = 1",
            *params,
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
            "WITH ranked_reviews AS ("
            "  SELECT entity_id, feedback_id, sentiment_label, confidence_score, "
            "    ROW_NUMBER() OVER ("
            "      PARTITION BY entity_id, feedback_id "
            "      ORDER BY (sentiment_label IS NOT NULL) DESC, "
            "        confidence_score DESC NULLS LAST, result_id DESC"
            "    ) AS review_rank "
            "  FROM fact_review_absa_results"
            "), review_stats AS ("
            "  SELECT entity_id, "
            "    COUNT(*)::int AS total_reviews, "
            "    COUNT(CASE WHEN sentiment_label = 'Positive' THEN 1 END)::int AS positive_count, "
            "    COUNT(CASE WHEN sentiment_label = 'Negative' THEN 1 END)::int AS negative_count, "
            "    COUNT(CASE WHEN sentiment_label = 'Neutral' THEN 1 END)::int AS neutral_count, "
            "    ROUND(COUNT(CASE WHEN sentiment_label = 'Positive' THEN 1 END)::NUMERIC "
            "      / NULLIF(COUNT(*) FILTER (WHERE sentiment_label IS NOT NULL), 0), 4) AS positive_ratio, "
            "    ROUND(COUNT(CASE WHEN sentiment_label = 'Negative' THEN 1 END)::NUMERIC "
            "      / NULLIF(COUNT(*) FILTER (WHERE sentiment_label IS NOT NULL), 0), 4) AS negative_ratio, "
            "    ROUND(AVG(confidence_score) FILTER (WHERE sentiment_label IS NOT NULL), 4) AS avg_confidence "
            "  FROM ranked_reviews WHERE review_rank = 1 GROUP BY entity_id"
            "), post_stats AS ("
            "  SELECT entity_id, COUNT(*)::int AS total_posts, "
            "    SUM(total_reactions)::bigint AS total_reactions, "
            "    SUM(shares_count)::bigint AS total_shares, "
            "    SUM(comments_count)::bigint AS total_comments "
            "  FROM fact_social_posts GROUP BY entity_id"
            ") "
            "SELECT de.entity_id, de.entity_name, de.platform, "
            "  COALESCE(ps.total_posts, 0)::int AS total_posts, "
            "  ps.total_reactions, ps.total_shares, ps.total_comments, "
            "  COALESCE(rs.total_reviews, 0)::int AS total_reviews, "
            "  COALESCE(rs.positive_count, 0)::int AS positive_count, "
            "  COALESCE(rs.negative_count, 0)::int AS negative_count, "
            "  COALESCE(rs.neutral_count, 0)::int AS neutral_count, "
            "  rs.positive_ratio, rs.negative_ratio, rs.avg_confidence "
            "FROM dim_entities de "
            "LEFT JOIN review_stats rs ON rs.entity_id = de.entity_id "
            "LEFT JOIN post_stats ps ON ps.entity_id = de.entity_id "
            "ORDER BY GREATEST(COALESCE(rs.total_reviews, 0), COALESCE(ps.total_posts, 0)) DESC, "
            "  de.entity_name"
        )
    return [
        EntitySentimentOverview(
            entity_id=r["entity_id"],
            entity_name=r["entity_name"],
            platform=r["platform"],
            total_posts=r["total_posts"] or 0,
            total_reactions=r["total_reactions"],
            total_shares=r["total_shares"],
            total_comments=r["total_comments"],
            total_reviews=r["total_reviews"] or 0,
            positive_count=r["positive_count"] or 0,
            negative_count=r["negative_count"] or 0,
            neutral_count=r["neutral_count"] or 0,
            positive_ratio=(
                float(r["positive_ratio"]) if r["positive_ratio"] is not None else None
            ),
            negative_ratio=(
                float(r["negative_ratio"]) if r["negative_ratio"] is not None else None
            ),
            avg_confidence=(
                float(r["avg_confidence"]) if r["avg_confidence"] is not None else None
            ),
        )
        for r in rows
    ]


async def get_aspect_breakdown(
    entity_id: int | None = None, days: int | None = None
) -> list[AspectBreakdown]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if entity_id is None and days is None:
            rows = await conn.fetch(
                "SELECT * FROM v_aspect_breakdown "
                "WHERE aspect_category IS NOT NULL "
                "  AND sentiment_label IS NOT NULL "
                "ORDER BY aspect_category, count DESC"
            )
        else:
            where, params = _review_filters(entity_id, days)
            complete_aspect_filter = (
                " AND aspect_category IS NOT NULL "
                "AND sentiment_label IS NOT NULL"
                if where
                else
                " WHERE aspect_category IS NOT NULL "
                "AND sentiment_label IS NOT NULL"
            )
            rows = await conn.fetch(
                "SELECT aspect_category, sentiment_label, "
                "  COUNT(*)::int AS count, "
                "  ROUND(AVG(confidence_score), 4) AS avg_confidence "
                f"FROM fact_review_absa_results{where}"
                f"{complete_aspect_filter} "
                "GROUP BY aspect_category, sentiment_label "
                "ORDER BY aspect_category, count DESC",
                *params,
            )
    return [
        AspectBreakdown(
            aspect=r["aspect_category"],
            sentiment=r["sentiment_label"],
            count=r["count"],
            avg_confidence=float(r["avg_confidence"]) if r["avg_confidence"] else 0,
        )
        for r in rows
        if r["aspect_category"] is not None and r["sentiment_label"] is not None
    ]


async def get_sentiment_trends(
    entity_id: int | None = None, days: int = 30
) -> list[SentimentTrendPoint]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if entity_id is not None:
            rows = await conn.fetch(
                "SELECT * FROM v_sentiment_daily_trends "
                "WHERE entity_id = $1 "
                "AND feedback_date >= CURRENT_DATE - ($2 * INTERVAL '1 day') "
                "ORDER BY feedback_date",
                entity_id,
                days,
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
                "WHERE feedback_date >= CURRENT_DATE - ($1 * INTERVAL '1 day') "
                "GROUP BY feedback_date ORDER BY feedback_date",
                days,
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


async def get_facebook_engagement(
    entity_id: int | None = None, days: int | None = None
) -> list[FacebookEngagement]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if entity_id is None and days is None:
            rows = await conn.fetch(
                "SELECT * FROM v_facebook_engagement ORDER BY total_reactions DESC NULLS LAST"
            )
        else:
            clauses: list[str] = []
            params: list = []
            if entity_id is not None:
                params.append(entity_id)
                clauses.append(f"p.entity_id = ${len(params)}")
            if days is not None:
                params.append(days)
                clauses.append(
                    f"p.post_timestamp >= CURRENT_DATE - (${len(params)} * INTERVAL '1 day')"
                )
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = await conn.fetch(
                "SELECT de.entity_id, de.entity_name, "
                "  COUNT(p.post_id)::int AS total_posts, "
                "  SUM(p.total_reactions)::bigint AS total_reactions, "
                "  SUM(p.shares_count)::bigint AS total_shares, "
                "  SUM(p.comments_count)::bigint AS total_comments, "
                "  ROUND(AVG(p.positivity_ratio) FILTER (WHERE p.like_count IS NOT NULL), 4) AS avg_positivity_ratio, "
                "  ROUND(AVG(p.negativity_ratio) FILTER (WHERE p.like_count IS NOT NULL), 4) AS avg_negativity_ratio "
                "FROM fact_social_posts p "
                "JOIN dim_entities de ON de.entity_id = p.entity_id"
                f"{where} "
                "GROUP BY de.entity_id, de.entity_name "
                "ORDER BY total_reactions DESC NULLS LAST",
                *params,
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


async def get_entity_aspect_summary(entity_id: int) -> list[EntityAspectItem]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT aspect_category, sentiment_label, count "
            "FROM v_entity_aspect_summary "
            "WHERE entity_id = $1 "
            "ORDER BY aspect_category, count DESC",
            entity_id,
        )
    return [
        EntityAspectItem(
            aspect_category=r["aspect_category"],
            sentiment_label=r["sentiment_label"],
            count=r["count"],
        )
        for r in rows
    ]


def _encode_review_cursor(created_at: datetime | None, result_id: int) -> str:
    payload = json.dumps(
        {
            "created_at": created_at.isoformat() if created_at else None,
            "result_id": result_id,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_review_cursor(cursor: str) -> tuple[datetime | None, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        created_at = (
            datetime.fromisoformat(payload["created_at"])
            if payload.get("created_at")
            else None
        )
        result_id = int(payload["result_id"])
        if result_id <= 0:
            raise ValueError
        return created_at, result_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid review cursor") from exc


def _entity_review_from_row(row) -> EntityReview:
    return EntityReview(
        feedback_id=str(row["feedback_id"]),
        review_text=row["review_text"],
        sentiment_label=row["sentiment_label"],
        confidence_score=(
            float(row["confidence_score"])
            if row["confidence_score"] is not None
            else None
        ),
        aspect_category=row["aspect_category"],
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )


async def get_entity_reviews(
    entity_id: int,
    *,
    days: int | None = 30,
    aspect: str | None = None,
    limit: int = 10,
    cursor: str | None = None,
    focus_feedback_id: str | None = None,
) -> EntityReviewPageResponse:
    clauses = ["entity_id = $1"]
    params: list = [entity_id]
    if days is not None:
        params.append(days)
        clauses.append(
            f"feedback_timestamp >= CURRENT_DATE - (${len(params)} * INTERVAL '1 day')"
        )
    if aspect:
        params.append(aspect)
        clauses.append(f"aspect_category = ${len(params)}")

    where = " AND ".join(clauses)
    cursor_clause = ""
    if cursor:
        cursor_timestamp, cursor_result_id = _decode_review_cursor(cursor)
        params.extend([cursor_timestamp, cursor_result_id])
        cursor_clause = (
            "AND (COALESCE(feedback_timestamp, TIMESTAMP '-infinity'), result_id) "
            f"< (COALESCE(${len(params) - 1}::timestamp, TIMESTAMP '-infinity'), "
            f"${len(params)}) "
        )
    params.append(limit + 1)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "WITH ranked AS ("
            "  SELECT result_id, feedback_id, raw_text AS review_text, "
            "    sentiment_label, confidence_score, aspect_category, "
            "    feedback_timestamp AS created_at, feedback_timestamp, "
            "    ROW_NUMBER() OVER ("
            "      PARTITION BY feedback_id "
            "      ORDER BY confidence_score DESC NULLS LAST, result_id DESC"
            "    ) AS review_rank "
            "  FROM fact_review_absa_results "
            f"  WHERE {where}"
            ") "
            "SELECT result_id, feedback_id, review_text, sentiment_label, "
            "  confidence_score, aspect_category, created_at "
            "FROM ranked WHERE review_rank = 1 "
            f"{cursor_clause}"
            "ORDER BY COALESCE(feedback_timestamp, TIMESTAMP '-infinity') DESC, "
            "  result_id DESC "
            f"LIMIT ${len(params)}",
            *params,
        )

        count_params = params[: 1 + int(days is not None) + int(bool(aspect))]
        total = await conn.fetchval(
            "SELECT COUNT(DISTINCT feedback_id)::int "
            "FROM fact_review_absa_results "
            f"WHERE {where}",
            *count_params,
        )

        focus_row = None
        if focus_feedback_id:
            focus_params: list = [entity_id, focus_feedback_id]
            focus_aspect_clause = ""
            if aspect:
                focus_params.append(aspect)
                focus_aspect_clause = f"AND aspect_category = ${len(focus_params)} "
            focus_row = await conn.fetchrow(
                "SELECT result_id, feedback_id, raw_text AS review_text, "
                "  sentiment_label, confidence_score, aspect_category, "
                "  feedback_timestamp AS created_at "
                "FROM fact_review_absa_results "
                "WHERE entity_id = $1 AND feedback_id = $2 "
                f"{focus_aspect_clause}"
                "ORDER BY confidence_score DESC NULLS LAST, result_id DESC "
                "LIMIT 1",
                *focus_params,
            )

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = _encode_review_cursor(last["created_at"], last["result_id"])

    return EntityReviewPageResponse(
        reviews=[_entity_review_from_row(row) for row in page_rows],
        total=int(total or 0),
        next_cursor=next_cursor,
        focus_review=_entity_review_from_row(focus_row) if focus_row else None,
    )


# ---------- Dashboard KPI strip ----------


def _sentiment_health(positive: int, neutral: int, total: int) -> float | None:
    """0-100 score: positive = 1pt, neutral = 0.5pt, negative = 0pt."""
    if not total:
        return None
    return round(100.0 * (positive + 0.5 * neutral) / total, 1)


async def get_kpis(entity_id: int | None = None, days: int = 30) -> KpiResponse:
    entity_clause = ""
    base_params: list = [days]
    if entity_id is not None:
        base_params.append(entity_id)
        entity_clause = f" AND entity_id = ${len(base_params)}"

    pool = await get_pool()
    async with pool.acquire() as conn:
        volume_rows = await conn.fetch(
            "SELECT DATE(feedback_timestamp) AS d, "
            "  COUNT(DISTINCT feedback_id)::int AS c "
            "FROM fact_review_absa_results "
            "WHERE feedback_timestamp >= CURRENT_DATE - ($1 * INTERVAL '1 day')"
            f"{entity_clause} "
            "GROUP BY d ORDER BY d",
            *base_params,
        )
        agg = await conn.fetchrow(
            "SELECT "
            "  COUNT(DISTINCT feedback_id) FILTER (WHERE feedback_timestamp >= CURRENT_DATE - ($1 * INTERVAL '1 day'))::int AS cur_total, "
            "  COUNT(DISTINCT feedback_id) FILTER (WHERE feedback_timestamp < CURRENT_DATE - ($1 * INTERVAL '1 day'))::int AS prev_total, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp >= CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label IS NOT NULL)::int AS cur_sentiment_total, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp < CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label IS NOT NULL)::int AS prev_sentiment_total, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp >= CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label = 'Positive')::int AS cur_pos, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp >= CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label = 'Neutral')::int AS cur_neu, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp < CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label = 'Positive')::int AS prev_pos, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp < CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label = 'Neutral')::int AS prev_neu "
            "FROM fact_review_absa_results "
            "WHERE feedback_timestamp >= CURRENT_DATE - (2 * $1 * INTERVAL '1 day')"
            f"{entity_clause}",
            *base_params,
        )
        hangry_params: list = [days, list(HANGRY_ASPECTS)]
        hangry_entity_clause = ""
        if entity_id is not None:
            hangry_params.append(entity_id)
            hangry_entity_clause = f" AND entity_id = ${len(hangry_params)}"
        hangry = await conn.fetchrow(
            "SELECT "
            "  COUNT(*) FILTER (WHERE feedback_timestamp >= CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label = 'Negative')::int AS cur_neg, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp >= CURRENT_DATE - ($1 * INTERVAL '1 day'))::int AS cur_total, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp < CURRENT_DATE - ($1 * INTERVAL '1 day') AND sentiment_label = 'Negative')::int AS prev_neg, "
            "  COUNT(*) FILTER (WHERE feedback_timestamp < CURRENT_DATE - ($1 * INTERVAL '1 day'))::int AS prev_total "
            "FROM fact_review_absa_results "
            "WHERE aspect_category = ANY($2::text[]) "
            "  AND feedback_timestamp >= CURRENT_DATE - (2 * $1 * INTERVAL '1 day')"
            f"{hangry_entity_clause}",
            *hangry_params,
        )

    cur_total = agg["cur_total"] or 0
    prev_total = agg["prev_total"] or 0
    volume_delta_pct = (
        round(100.0 * (cur_total - prev_total) / prev_total, 1) if prev_total else None
    )
    health = _sentiment_health(
        agg["cur_pos"] or 0,
        agg["cur_neu"] or 0,
        agg["cur_sentiment_total"] or 0,
    )
    prev_health = _sentiment_health(
        agg["prev_pos"] or 0,
        agg["prev_neu"] or 0,
        agg["prev_sentiment_total"] or 0,
    )
    health_delta = (
        round(health - prev_health, 1)
        if health is not None and prev_health is not None
        else None
    )

    hangry_cur = (
        round(hangry["cur_neg"] / hangry["cur_total"], 4) if hangry["cur_total"] else None
    )
    hangry_prev = (
        round(hangry["prev_neg"] / hangry["prev_total"], 4)
        if hangry["prev_total"]
        else None
    )
    hangry_delta = (
        round(hangry_cur - hangry_prev, 4)
        if hangry_cur is not None and hangry_prev is not None
        else None
    )

    return KpiResponse(
        total_reviews=cur_total,
        prev_total_reviews=prev_total,
        volume_delta_pct=volume_delta_pct,
        daily_volumes=[
            DailyVolume(date=str(r["d"]), count=r["c"]) for r in volume_rows
        ],
        sentiment_health=health,
        sentiment_health_delta=health_delta,
        hangry_index=hangry_cur,
        hangry_delta=hangry_delta,
    )


# ---------- Social engagement (Facebook reactions) ----------


async def get_reaction_mix(
    entity_id: int | None = None, days: int | None = None
) -> ReactionMix:
    where, params = _post_filters(entity_id, days)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT "
            "  COALESCE(SUM(like_count), 0)::bigint AS like, "
            "  COALESCE(SUM(love_count), 0)::bigint AS love, "
            "  COALESCE(SUM(care_count), 0)::bigint AS care, "
            "  COALESCE(SUM(haha_count), 0)::bigint AS haha, "
            "  COALESCE(SUM(wow_count), 0)::bigint AS wow, "
            "  COALESCE(SUM(sad_count), 0)::bigint AS sad, "
            "  COALESCE(SUM(angry_count), 0)::bigint AS angry, "
            "  COUNT(*)::int AS total_posts, "
            "  COUNT(*) FILTER (WHERE like_count IS NULL OR total_reactions IS NULL)::int AS incomplete_posts, "
            "  ROUND(AVG(positivity_ratio) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL), 4) AS positivity_ratio, "
            "  ROUND(AVG(negativity_ratio) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL), 4) AS negativity_ratio, "
            "  ROUND((SUM(haha_count) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL))::NUMERIC "
            "    / NULLIF(SUM(total_reactions) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL), 0), 4) AS haha_ratio "
            f"FROM fact_social_posts{where}",
            *params,
        )
    return ReactionMix(
        like=row["like"] or 0,
        love=row["love"] or 0,
        care=row["care"] or 0,
        haha=row["haha"] or 0,
        wow=row["wow"] or 0,
        sad=row["sad"] or 0,
        angry=row["angry"] or 0,
        total_posts=row["total_posts"] or 0,
        incomplete_posts=row["incomplete_posts"] or 0,
        positivity_ratio=(
            float(row["positivity_ratio"]) if row["positivity_ratio"] is not None else None
        ),
        negativity_ratio=(
            float(row["negativity_ratio"]) if row["negativity_ratio"] is not None else None
        ),
        haha_ratio=float(row["haha_ratio"]) if row["haha_ratio"] is not None else None,
    )


async def get_engagement_trends(
    entity_id: int | None = None, days: int = 30
) -> list[EngagementTrendPoint]:
    where, params = _post_filters(entity_id, days)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DATE(post_timestamp) AS d, "
            "  SUM(total_reactions)::bigint AS total_reactions, "
            "  SUM(shares_count)::bigint AS total_shares, "
            "  SUM(comments_count)::bigint AS total_comments, "
            "  ROUND(AVG(positivity_ratio) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL), 4) AS positivity_ratio, "
            "  ROUND(AVG(negativity_ratio) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL), 4) AS negativity_ratio, "
            "  ROUND((SUM(haha_count) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL))::NUMERIC "
            "    / NULLIF(SUM(total_reactions) FILTER (WHERE like_count IS NOT NULL AND total_reactions IS NOT NULL), 0), 4) AS haha_ratio "
            f"FROM fact_social_posts{where} "
            "GROUP BY d ORDER BY d",
            *params,
        )
    return [
        EngagementTrendPoint(
            date=str(r["d"]),
            total_reactions=r["total_reactions"],
            total_shares=r["total_shares"],
            total_comments=r["total_comments"],
            positivity_ratio=(
                float(r["positivity_ratio"]) if r["positivity_ratio"] is not None else None
            ),
            negativity_ratio=(
                float(r["negativity_ratio"]) if r["negativity_ratio"] is not None else None
            ),
            haha_ratio=float(r["haha_ratio"]) if r["haha_ratio"] is not None else None,
        )
        for r in rows
    ]


# ---------- Top drivers & flagged reviews ----------


async def get_top_drivers(
    entity_id: int | None = None, days: int | None = None, limit: int = 8
) -> list[DriverItem]:
    where, params = _review_filters(entity_id, days)
    where += (
        " AND aspect_category IS NOT NULL AND aspect_category <> 'no_aspect'"
        if where
        else " WHERE aspect_category IS NOT NULL AND aspect_category <> 'no_aspect'"
    )
    params.append(limit)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT aspect_category AS aspect, "
            "  COUNT(*) FILTER (WHERE sentiment_label = 'Negative')::int AS negative_count, "
            "  COUNT(*)::int AS total_count, "
            "  ROUND(COUNT(*) FILTER (WHERE sentiment_label = 'Negative')::NUMERIC / NULLIF(COUNT(*), 0), 4) AS negative_share, "
            "  ROUND(AVG(confidence_score), 4) AS avg_confidence "
            f"FROM fact_review_absa_results{where} "
            "GROUP BY aspect_category "
            "ORDER BY negative_count DESC, total_count DESC "
            f"LIMIT ${len(params)}",
            *params,
        )
    return [
        DriverItem(
            aspect=r["aspect"],
            negative_count=r["negative_count"],
            total_count=r["total_count"],
            negative_share=float(r["negative_share"] or 0),
            avg_confidence=(
                float(r["avg_confidence"]) if r["avg_confidence"] is not None else None
            ),
        )
        for r in rows
    ]


async def get_flagged_reviews(
    entity_id: int | None = None,
    days: int | None = None,
    aspect: str | None = None,
    limit: int = 5,
) -> list[FlaggedReview]:
    clauses = ["r.sentiment_label = 'Negative'"]
    params: list = []
    if entity_id is not None:
        params.append(entity_id)
        clauses.append(f"r.entity_id = ${len(params)}")
    if days is not None:
        params.append(days)
        clauses.append(
            f"r.feedback_timestamp >= CURRENT_DATE - (${len(params)} * INTERVAL '1 day')"
        )
    if aspect is not None:
        params.append(aspect)
        clauses.append(f"r.aspect_category = ${len(params)}")
    params.append(limit)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT r.raw_text AS review_text, r.sentiment_label, r.confidence_score, "
            "  r.aspect_category, de.entity_name, r.feedback_timestamp AS created_at "
            "FROM fact_review_absa_results r "
            "LEFT JOIN dim_entities de ON de.entity_id = r.entity_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY r.feedback_timestamp DESC NULLS LAST, r.result_id DESC "
            f"LIMIT ${len(params)}",
            *params,
        )
    return [
        FlaggedReview(
            review_text=r["review_text"],
            sentiment_label=r["sentiment_label"],
            confidence_score=(
                float(r["confidence_score"]) if r["confidence_score"] is not None else None
            ),
            aspect_category=r["aspect_category"],
            entity_name=r["entity_name"],
            created_at=str(r["created_at"]) if r["created_at"] else None,
        )
        for r in rows
    ]
