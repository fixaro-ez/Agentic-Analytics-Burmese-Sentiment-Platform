from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import AuthUser, get_current_user
from ..models.analytics import (
    AspectBreakdown,
    AspectBreakdownListResponse,
    EntityDetailResponse,
    EntitySentimentListResponse,
    EntitySentimentOverview,
    FacebookEngagement,
    FacebookEngagementListResponse,
    SentimentOverview,
    SentimentTrendListResponse,
    SentimentTrendPoint,
)
from ..services.analytics import (
    get_aspect_breakdown,
    get_entity_aspect_summary,
    get_entity_reviews,
    get_entity_sentiment_overviews,
    get_facebook_engagement,
    get_sentiment_overview,
    get_sentiment_trends,
)
from ..services.entities import get_entity_by_id

router = APIRouter()


@router.get("/overview", response_model=SentimentOverview)
async def sentiment_overview(user: AuthUser = Depends(get_current_user)):
    return await get_sentiment_overview()


@router.get("/entities", response_model=EntitySentimentListResponse)
async def entity_overviews(user: AuthUser = Depends(get_current_user)):
    items = await get_entity_sentiment_overviews()
    return EntitySentimentListResponse(entities=items, total=len(items))


@router.get("/aspects", response_model=AspectBreakdownListResponse)
async def aspect_breakdown(user: AuthUser = Depends(get_current_user)):
    items = await get_aspect_breakdown()
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
async def facebook_engagement(user: AuthUser = Depends(get_current_user)):
    items = await get_facebook_engagement()
    return FacebookEngagementListResponse(engagement=items)


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
    reviews = await get_entity_reviews(entity_id)

    return EntityDetailResponse(
        entity_id=entity.entity_id,
        entity_name=entity.entity_name,
        platform=entity.platform,
        total_reviews=overview.total_reviews if overview else 0,
        positive_count=overview.positive_count if overview else 0,
        negative_count=overview.negative_count if overview else 0,
        neutral_count=overview.neutral_count if overview else 0,
        positive_ratio=overview.positive_ratio if overview else None,
        negative_ratio=overview.negative_ratio if overview else None,
        avg_confidence=overview.avg_confidence if overview else None,
        aspects=aspects,
        reviews=reviews,
    )
