from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import AuthUser, get_current_user
from ..models.analytics import (
    AspectBreakdown,
    AspectBreakdownListResponse,
    DriverListResponse,
    EngagementTrendListResponse,
    EntityDetailResponse,
    EntityReviewPageResponse,
    EntitySentimentListResponse,
    EntitySentimentOverview,
    FacebookEngagement,
    FacebookEngagementListResponse,
    FlaggedReviewListResponse,
    KpiResponse,
    ReactionMix,
    SentimentOverview,
    SentimentTrendListResponse,
    SentimentTrendPoint,
)
from ..models.benchmark import BenchmarkResponse
from ..services.analytics import (
    get_aspect_breakdown,
    get_engagement_trends,
    get_entity_aspect_summary,
    get_entity_reviews,
    get_entity_sentiment_overviews,
    get_facebook_engagement,
    get_flagged_reviews,
    get_kpis,
    get_reaction_mix,
    get_sentiment_overview,
    get_sentiment_trends,
    get_top_drivers,
)
from ..services.benchmark import get_competitor_benchmark
from ..services.entities import get_entity_by_id

router = APIRouter()

DaysFilter = Query(default=None, ge=1, le=365)
AspectFilter = Literal[
    "product_or_service_quality",
    "fulfillment_and_speed",
    "price_and_value",
    "digital_experience",
    "customer_support",
    "variety_and_availability",
]


@router.get("/overview", response_model=SentimentOverview)
async def sentiment_overview(
    entity_id: int | None = None,
    days: int | None = DaysFilter,
    user: AuthUser = Depends(get_current_user),
):
    return await get_sentiment_overview(entity_id=entity_id, days=days)


@router.get("/entities", response_model=EntitySentimentListResponse)
async def entity_overviews(user: AuthUser = Depends(get_current_user)):
    items = await get_entity_sentiment_overviews()
    return EntitySentimentListResponse(entities=items, total=len(items))


@router.get("/aspects", response_model=AspectBreakdownListResponse)
async def aspect_breakdown(
    entity_id: int | None = None,
    days: int | None = DaysFilter,
    user: AuthUser = Depends(get_current_user),
):
    items = await get_aspect_breakdown(entity_id=entity_id, days=days)
    return AspectBreakdownListResponse(aspects=items)


@router.get("/trends", response_model=SentimentTrendListResponse)
async def sentiment_trends(
    entity_id: int | None = None,
    days: int = Query(default=30, ge=1, le=365),
    user: AuthUser = Depends(get_current_user),
):
    items = await get_sentiment_trends(entity_id=entity_id, days=days)
    return SentimentTrendListResponse(trends=items)


@router.get("/engagement", response_model=FacebookEngagementListResponse)
async def facebook_engagement(
    entity_id: int | None = None,
    days: int | None = DaysFilter,
    user: AuthUser = Depends(get_current_user),
):
    items = await get_facebook_engagement(entity_id=entity_id, days=days)
    return FacebookEngagementListResponse(engagement=items)


@router.get("/kpis", response_model=KpiResponse)
async def dashboard_kpis(
    entity_id: int | None = None,
    days: int = Query(default=30, ge=1, le=365),
    user: AuthUser = Depends(get_current_user),
):
    return await get_kpis(entity_id=entity_id, days=days)


@router.get("/engagement/reactions", response_model=ReactionMix)
async def reaction_mix(
    entity_id: int | None = None,
    days: int | None = DaysFilter,
    user: AuthUser = Depends(get_current_user),
):
    return await get_reaction_mix(entity_id=entity_id, days=days)


@router.get("/engagement/trends", response_model=EngagementTrendListResponse)
async def engagement_trends(
    entity_id: int | None = None,
    days: int = Query(default=30, ge=1, le=365),
    user: AuthUser = Depends(get_current_user),
):
    items = await get_engagement_trends(entity_id=entity_id, days=days)
    return EngagementTrendListResponse(trends=items)


@router.get("/drivers", response_model=DriverListResponse)
async def top_drivers(
    entity_id: int | None = None,
    days: int | None = DaysFilter,
    limit: int = Query(default=8, ge=1, le=50),
    user: AuthUser = Depends(get_current_user),
):
    items = await get_top_drivers(entity_id=entity_id, days=days, limit=limit)
    return DriverListResponse(drivers=items)


@router.get("/reviews/flagged", response_model=FlaggedReviewListResponse)
async def flagged_reviews(
    entity_id: int | None = None,
    days: int | None = DaysFilter,
    aspect: AspectFilter | None = None,
    limit: int = Query(default=5, ge=1, le=50),
    user: AuthUser = Depends(get_current_user),
):
    items = await get_flagged_reviews(
        entity_id=entity_id, days=days, aspect=aspect, limit=limit
    )
    return FlaggedReviewListResponse(reviews=items)


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse)
async def entity_detail(
    entity_id: int,
    user: AuthUser = Depends(get_current_user),
):
    entity = await get_entity_by_id(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    overviews = await get_entity_sentiment_overviews()
    overview = next((o for o in overviews if o.entity_id == entity_id), None)

    aspects = await get_entity_aspect_summary(entity_id)

    return EntityDetailResponse(
        entity_id=entity.entity_id,
        entity_name=entity.entity_name,
        platform=entity.platform,
        total_posts=overview.total_posts if overview else 0,
        total_reactions=overview.total_reactions if overview else None,
        total_shares=overview.total_shares if overview else None,
        total_comments=overview.total_comments if overview else None,
        total_reviews=overview.total_reviews if overview else 0,
        positive_count=overview.positive_count if overview else 0,
        negative_count=overview.negative_count if overview else 0,
        neutral_count=overview.neutral_count if overview else 0,
        positive_ratio=overview.positive_ratio if overview else None,
        negative_ratio=overview.negative_ratio if overview else None,
        avg_confidence=overview.avg_confidence if overview else None,
        aspects=aspects,
    )


@router.get(
    "/entities/{entity_id}/reviews",
    response_model=EntityReviewPageResponse,
)
async def entity_reviews(
    entity_id: int,
    days: int | None = DaysFilter,
    aspect: AspectFilter | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=512),
    focus_feedback_id: str | None = Query(default=None, max_length=100),
    user: AuthUser = Depends(get_current_user),
):
    if await get_entity_by_id(entity_id) is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    try:
        return await get_entity_reviews(
            entity_id,
            days=days,
            aspect=aspect,
            limit=limit,
            cursor=cursor,
            focus_feedback_id=focus_feedback_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/benchmark", response_model=BenchmarkResponse)
async def competitor_benchmark(
    brand_a_id: int = Query(gt=0),
    brand_b_id: int = Query(gt=0),
    brand_a_branch_ids: list[int] | None = Query(default=None),
    brand_b_branch_ids: list[int] | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    minimum_reviews: int = Query(default=30, ge=1, le=10000),
    delta_threshold: float = Query(default=0.10, ge=0, le=1),
    user: AuthUser = Depends(get_current_user),
):
    try:
        return await get_competitor_benchmark(
            brand_a_id,
            brand_b_id,
            brand_a_branch_ids=brand_a_branch_ids,
            brand_b_branch_ids=brand_b_branch_ids,
            days=days,
            minimum_reviews=minimum_reviews,
            delta_threshold=delta_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
