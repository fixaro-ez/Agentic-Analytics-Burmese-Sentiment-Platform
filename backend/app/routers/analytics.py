from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import AuthUser, get_current_user
from ..models.analytics import (
    AspectBreakdown,
    AspectBreakdownListResponse,
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
    get_entity_sentiment_overviews,
    get_facebook_engagement,
    get_sentiment_overview,
    get_sentiment_trends,
)

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
