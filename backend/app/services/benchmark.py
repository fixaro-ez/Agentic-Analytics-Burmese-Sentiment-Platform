from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..database import get_pool
from ..models.benchmark import (
    BenchmarkAspectCell,
    BenchmarkBrand,
    BenchmarkFilterSummary,
    BenchmarkInsight,
    BenchmarkMeta,
    BenchmarkResponse,
    BrandSelection,
)
from .brands import list_brands

BENCHMARK_MIN_REVIEWS = 30
BENCHMARK_DELTA_THRESHOLD = 0.10

BENCHMARK_ASSUMPTIONS = [
    "A brand combines its one mapped Facebook page with the selected mapped Foodpanda branches.",
    "Facebook weighted engagement is (reactions + 2x comments + 3x shares) x (1 + 0.20x positive engagement ratio - 0.20x negative engagement ratio).",
    "Facebook share uses weighted engagement from every page post in the selected range; posting volume is shown separately.",
    "Foodpanda share is each brand's share of distinct Foodpanda reviews in the selected range.",
    "Combined share of voice is 50% Facebook weighted-engagement share plus 50% Foodpanda review-volume share. It is unavailable if either channel has no observations.",
    "Aspect net sentiment is (positive - negative) / all Foodpanda ABSA observations for that aspect.",
    "A brand needs 30 distinct Foodpanda reviews across its selected branches; below-threshold sentiment and head-to-head conclusions are suppressed.",
]


def validate_brand_selection(brand_a_id: int, brand_b_id: int) -> tuple[int, int]:
    if brand_a_id <= 0 or brand_b_id <= 0:
        raise ValueError("Brand IDs must be positive integers.")
    if brand_a_id == brand_b_id:
        raise ValueError("Choose two different brands.")
    return brand_a_id, brand_b_id


def _resolve_branches(brand, selected: list[int] | None) -> list[int]:
    mapped = [shop.entity_id for shop in brand.foodpanda_shops]
    chosen = list(dict.fromkeys(selected or mapped))
    if not chosen:
        raise ValueError(f"{brand.brand_name} has no selected Foodpanda branches.")
    invalid = [entity_id for entity_id in chosen if entity_id not in mapped]
    if invalid:
        raise ValueError(
            f"Foodpanda branches are not mapped to {brand.brand_name}: "
            f"{', '.join(map(str, invalid))}."
        )
    return chosen


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, TypeError):
        return default
    return default if value is None else value



def _net_sentiment(positive: float, negative: float, total: float) -> float | None:
    if total <= 0:
        return None
    return round((positive - negative) / total, 4)


async def get_competitor_benchmark(
    brand_a_id: int,
    brand_b_id: int,
    *,
    brand_a_branch_ids: list[int] | None = None,
    brand_b_branch_ids: list[int] | None = None,
    days: int = 30,
    minimum_reviews: int = BENCHMARK_MIN_REVIEWS,
    delta_threshold: float = BENCHMARK_DELTA_THRESHOLD,
) -> BenchmarkResponse:
    selected_ids = validate_brand_selection(brand_a_id, brand_b_id)
    brand_map = {brand.brand_id: brand for brand in await list_brands()}
    missing = [brand_id for brand_id in selected_ids if brand_id not in brand_map]
    if missing:
        raise ValueError(f"Unknown brand IDs: {', '.join(map(str, missing))}.")
    selected_brands = [brand_map[brand_id] for brand_id in selected_ids]
    branches = {
        brand_a_id: _resolve_branches(selected_brands[0], brand_a_branch_ids),
        brand_b_id: _resolve_branches(selected_brands[1], brand_b_branch_ids),
    }
    fb_brand_ids = list(selected_ids)
    fb_entity_ids = [brand.facebook_entity.entity_id for brand in selected_brands]
    flat_brand_ids = [
        brand_id for brand_id in selected_ids for _ in branches[brand_id]
    ]
    flat_shop_ids = [
        shop_id for brand_id in selected_ids for shop_id in branches[brand_id]
    ]

    pool = await get_pool()
    async with pool.acquire() as conn:
        facebook_rows = await conn.fetch(
            """
            WITH selected(brand_id, entity_id) AS (
                SELECT * FROM UNNEST($1::int[], $2::int[])
            )
            SELECT selected.brand_id,
                   COUNT(p.post_id)::int AS post_count,
                   COALESCE(SUM(
                     (
                       COALESCE(
                         p.total_reactions,
                         COALESCE(p.like_count, 0) + COALESCE(p.love_count, 0)
                         + COALESCE(p.care_count, 0) + COALESCE(p.haha_count, 0)
                         + COALESCE(p.wow_count, 0) + COALESCE(p.sad_count, 0)
                         + COALESCE(p.angry_count, 0)
                       )
                       + 2 * COALESCE(p.comments_count, 0)
                       + 3 * COALESCE(p.shares_count, 0)
                     ) * (
                       1 + 0.20 * COALESCE(p.positivity_ratio, 0)
                         - 0.20 * COALESCE(p.negativity_ratio, 0)
                     )
                   ), 0)::float AS weighted_engagement
            FROM selected
            LEFT JOIN fact_social_posts p
              ON p.entity_id = selected.entity_id
             AND p.post_timestamp >= CURRENT_DATE - ($3 * INTERVAL '1 day')
            GROUP BY selected.brand_id
            """,
            fb_brand_ids,
            fb_entity_ids,
            days,
        )
        review_rows = await conn.fetch(
            """
            WITH selected(brand_id, entity_id) AS (
                SELECT * FROM UNNEST($1::int[], $2::int[])
            )
            SELECT selected.brand_id,
                   COUNT(DISTINCT r.feedback_id)::int AS review_count,
                   COUNT(r.result_id)::int AS observation_count,
                   COUNT(*) FILTER (WHERE r.sentiment_label = 'Positive')::int
                     AS positive_count,
                   COUNT(*) FILTER (WHERE r.sentiment_label = 'Negative')::int
                     AS negative_count
            FROM selected
            LEFT JOIN fact_review_absa_results r
              ON r.entity_id = selected.entity_id
             AND r.feedback_timestamp >= CURRENT_DATE - ($3 * INTERVAL '1 day')
            GROUP BY selected.brand_id
            """,
            flat_brand_ids,
            flat_shop_ids,
            days,
        )
        aspect_rows = await conn.fetch(
            """
            WITH selected(brand_id, entity_id) AS (
                SELECT * FROM UNNEST($1::int[], $2::int[])
            )
            SELECT selected.brand_id, r.aspect_category AS aspect,
                   COUNT(*)::int AS observation_count,
                   COUNT(*) FILTER (WHERE r.sentiment_label = 'Positive')::int
                     AS positive_count,
                   COUNT(*) FILTER (WHERE r.sentiment_label = 'Negative')::int
                     AS negative_count,
                   COUNT(*) FILTER (WHERE r.sentiment_label = 'Neutral')::int
                     AS neutral_count
            FROM selected
            JOIN fact_review_absa_results r ON r.entity_id = selected.entity_id
            WHERE r.feedback_timestamp >= CURRENT_DATE - ($3 * INTERVAL '1 day')
              AND r.aspect_category IS NOT NULL
              AND r.aspect_category <> 'no_aspect'
            GROUP BY selected.brand_id, r.aspect_category
            ORDER BY r.aspect_category, selected.brand_id
            """,
            flat_brand_ids,
            flat_shop_ids,
            days,
        )

    fb_stats = {int(row["brand_id"]): row for row in facebook_rows}
    review_stats = {int(row["brand_id"]): row for row in review_rows}
    review_counts = {
        brand_id: int(_row_value(review_stats.get(brand_id, {}), "review_count", 0))
        for brand_id in selected_ids
    }
    eligibility = {
        brand_id: count >= minimum_reviews
        for brand_id, count in review_counts.items()
    }
    fb_total = sum(
        float(_row_value(fb_stats.get(brand_id, {}), "weighted_engagement", 0))
        for brand_id in selected_ids
    )
    review_total = sum(review_counts.values())
    channel_shares_available = fb_total > 0 and review_total > 0

    brands: list[BenchmarkBrand] = []
    for brand in selected_brands:
        brand_id = brand.brand_id
        fb_row = fb_stats.get(brand_id, {})
        review_row = review_stats.get(brand_id, {})
        weighted = float(_row_value(fb_row, "weighted_engagement", 0))
        facebook_share = round(weighted / fb_total, 4) if fb_total else None
        foodpanda_share = (
            round(review_counts[brand_id] / review_total, 4) if review_total else None
        )
        net = _net_sentiment(
            int(_row_value(review_row, "positive_count", 0)),
            int(_row_value(review_row, "negative_count", 0)),
            int(_row_value(review_row, "observation_count", 0)),
        )
        brands.append(
            BenchmarkBrand(
                brand_id=brand_id,
                brand_name=brand.brand_name,
                facebook_entity_id=brand.facebook_entity.entity_id,
                foodpanda_entity_ids=branches[brand_id],
                review_count=review_counts[brand_id],
                eligible=eligibility[brand_id],
                facebook_post_count=int(_row_value(fb_row, "post_count", 0)),
                facebook_weighted_engagement=round(weighted, 4),
                facebook_share=facebook_share,
                foodpanda_share=foodpanda_share,
                combined_share_of_voice=(
                    round(0.5 * facebook_share + 0.5 * foodpanda_share, 4)
                    if facebook_share is not None and foodpanda_share is not None
                    else None
                ),
                net_sentiment=net if eligibility[brand_id] else None,
                warning=(
                    None
                    if eligibility[brand_id]
                    else f"{review_counts[brand_id]} reviews; {minimum_reviews} required."
                ),
            )
        )

    aspects: list[BenchmarkAspectCell] = []
    aspect_values: dict[tuple[int, str], float] = {}
    for row in aspect_rows:
        brand_id = int(row["brand_id"])
        total = int(row["observation_count"])
        net = _net_sentiment(
            int(row["positive_count"]), int(row["negative_count"]), total
        )
        if eligibility[brand_id] and net is not None:
            aspect_values[(brand_id, row["aspect"])] = net
        aspects.append(
            BenchmarkAspectCell(
                brand_id=brand_id,
                aspect=row["aspect"],
                observation_count=total,
                positive_count=int(row["positive_count"]),
                negative_count=int(row["negative_count"]),
                neutral_count=int(row["neutral_count"]),
                net_sentiment=net if eligibility[brand_id] else None,
                eligible=eligibility[brand_id],
            )
        )

    insights: list[BenchmarkInsight] = []
    if all(eligibility.values()):
        compared_aspects = sorted(
            {
                aspect
                for bid, aspect in aspect_values
                if bid == brand_a_id and (brand_b_id, aspect) in aspect_values
            }
        )
        for aspect in compared_aspects:
            delta = round(
                aspect_values[(brand_a_id, aspect)]
                - aspect_values[(brand_b_id, aspect)],
                4,
            )
            if abs(delta) >= delta_threshold:
                insights.append(
                    BenchmarkInsight(
                        kind="advantage" if delta > 0 else "vulnerability",
                        aspect=aspect,
                        primary_brand_id=brand_a_id,
                        competitor_brand_id=brand_b_id,
                        delta=delta,
                    )
                )
    insights.sort(key=lambda item: abs(item.delta), reverse=True)
    eligible_count = sum(eligibility.values())
    return BenchmarkResponse(
        brands=brands,
        aspects=aspects,
        insights=insights,
        meta=BenchmarkMeta(
            filters=BenchmarkFilterSummary(
                brands=[
                    BrandSelection(
                        brand_id=brand_id,
                        foodpanda_entity_ids=branches[brand_id],
                    )
                    for brand_id in selected_ids
                ],
                days=days,
            ),
            minimum_reviews=minimum_reviews,
            delta_threshold=delta_threshold,
            sufficient_data=eligible_count == 2,
            eligible_brand_count=eligible_count,
            channel_shares_available=channel_shares_available,
            assumptions=BENCHMARK_ASSUMPTIONS,
        ),
    )
