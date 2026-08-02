from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class BrandSelection(BaseModel):
    brand_id: int
    foodpanda_entity_ids: list[int]


class BenchmarkFilterSummary(BaseModel):
    brands: list[BrandSelection]
    days: int


class BenchmarkBrand(BaseModel):
    brand_id: int
    brand_name: str
    facebook_entity_id: int
    foodpanda_entity_ids: list[int]
    review_count: int
    eligible: bool
    facebook_post_count: int
    facebook_weighted_engagement: float
    facebook_share: float | None = None
    foodpanda_share: float | None = None
    combined_share_of_voice: float | None = None
    net_sentiment: float | None = None
    warning: str | None = None


class BenchmarkAspectCell(BaseModel):
    brand_id: int
    aspect: str
    observation_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    net_sentiment: float | None = None
    eligible: bool


class BenchmarkInsight(BaseModel):
    kind: Literal["advantage", "vulnerability"]
    aspect: str
    primary_brand_id: int
    competitor_brand_id: int
    delta: float


class BenchmarkMeta(BaseModel):
    filters: BenchmarkFilterSummary
    minimum_reviews: int
    delta_threshold: float
    sufficient_data: bool
    eligible_brand_count: int
    channel_shares_available: bool
    assumptions: list[str]


class BenchmarkResponse(BaseModel):
    brands: list[BenchmarkBrand]
    aspects: list[BenchmarkAspectCell]
    insights: list[BenchmarkInsight]
    meta: BenchmarkMeta
