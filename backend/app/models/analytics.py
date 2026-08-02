from __future__ import annotations

from pydantic import BaseModel


class SentimentOverview(BaseModel):
    total_reviews: int
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_ratio: float
    negative_ratio: float
    avg_confidence: float | None = None


class AspectBreakdown(BaseModel):
    aspect: str
    sentiment: str
    count: int
    avg_confidence: float


class SentimentTrendPoint(BaseModel):
    date: str
    entity_id: int | None = None
    entity_name: str | None = None
    total_reviews: int
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_ratio: float


class EntitySentimentOverview(BaseModel):
    entity_id: int
    entity_name: str
    platform: str
    total_posts: int = 0
    total_reactions: int | None = None
    total_shares: int | None = None
    total_comments: int | None = None
    total_reviews: int
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_ratio: float | None = None
    negative_ratio: float | None = None
    avg_confidence: float | None = None


class FacebookEngagement(BaseModel):
    entity_id: int
    entity_name: str
    total_posts: int
    total_reactions: int | None = None
    total_shares: int | None = None
    total_comments: int | None = None
    avg_positivity_ratio: float | None = None
    avg_negativity_ratio: float | None = None


class AnalyticsDashboard(BaseModel):
    overview: SentimentOverview
    entity_overviews: list[EntitySentimentOverview]
    aspect_breakdown: list[AspectBreakdown]
    facebook_engagement: list[FacebookEngagement]


# ---------- Wrapper models for list endpoints ----------
# Frontend hooks expect { "key": [...] } not bare arrays.

class EntitySentimentListResponse(BaseModel):
    entities: list[EntitySentimentOverview]
    total: int


class AspectBreakdownListResponse(BaseModel):
    aspects: list[AspectBreakdown]


class SentimentTrendListResponse(BaseModel):
    trends: list[SentimentTrendPoint]


class FacebookEngagementListResponse(BaseModel):
    engagement: list[FacebookEngagement]


# ---------- Dashboard KPI strip ----------


class DailyVolume(BaseModel):
    date: str
    count: int


class KpiResponse(BaseModel):
    total_reviews: int
    prev_total_reviews: int
    volume_delta_pct: float | None = None
    daily_volumes: list[DailyVolume]
    sentiment_health: float | None = None  # 0-100
    sentiment_health_delta: float | None = None  # percentage points vs prev window
    hangry_index: float | None = None  # 0-1
    hangry_delta: float | None = None  # delta vs prev window


# ---------- Social engagement (Facebook reactions) ----------


class ReactionMix(BaseModel):
    like: int
    love: int
    care: int
    haha: int
    wow: int
    sad: int
    angry: int
    total_posts: int
    incomplete_posts: int
    positivity_ratio: float | None = None
    negativity_ratio: float | None = None
    haha_ratio: float | None = None


class EngagementTrendPoint(BaseModel):
    date: str
    total_reactions: int | None = None
    total_shares: int | None = None
    total_comments: int | None = None
    positivity_ratio: float | None = None
    negativity_ratio: float | None = None
    haha_ratio: float | None = None


class EngagementTrendListResponse(BaseModel):
    trends: list[EngagementTrendPoint]


# ---------- Top drivers & flagged reviews ----------


class DriverItem(BaseModel):
    aspect: str
    negative_count: int
    total_count: int
    negative_share: float
    avg_confidence: float | None = None


class DriverListResponse(BaseModel):
    drivers: list[DriverItem]


class FlaggedReview(BaseModel):
    review_text: str | None = None
    sentiment_label: str | None = None
    confidence_score: float | None = None
    aspect_category: str | None = None
    entity_name: str | None = None
    created_at: str | None = None


class FlaggedReviewListResponse(BaseModel):
    reviews: list[FlaggedReview]


class EntityAspectItem(BaseModel):
    aspect_category: str
    sentiment_label: str
    count: int


class EntityReview(BaseModel):
    feedback_id: str
    review_text: str | None = None
    sentiment_label: str | None = None
    confidence_score: float | None = None
    aspect_category: str | None = None
    created_at: str | None = None


class EntityReviewPageResponse(BaseModel):
    reviews: list[EntityReview]
    total: int
    next_cursor: str | None = None
    focus_review: EntityReview | None = None


class EntityDetailResponse(BaseModel):
    entity_id: int
    entity_name: str
    platform: str
    total_posts: int = 0
    total_reactions: int | None = None
    total_shares: int | None = None
    total_comments: int | None = None
    total_reviews: int
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_ratio: float | None = None
    negative_ratio: float | None = None
    avg_confidence: float | None = None
    aspects: list[EntityAspectItem]
