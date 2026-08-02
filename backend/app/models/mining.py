from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


MiningAxis = Literal[
    "positive_ratio",
    "negative_ratio",
    "avg_confidence",
    "total_reviews",
]
ClusterAlgorithm = Literal["kmeans", "hierarchical"]


class MiningFilterSummary(BaseModel):
    entity_ids: list[int]
    days: int | None = None


class AssociationRuleSample(BaseModel):
    feedback_id: str
    entity_id: int | None = None
    entity_name: str | None = None
    review_text: str | None = None
    created_at: str | None = None


class AssociationRuleResult(BaseModel):
    antecedent: list[str]
    consequent: list[str]
    support: float
    confidence: float
    lift: float
    cooccurrence_count: int = 0
    samples: list[AssociationRuleSample] = Field(default_factory=list)


class AssociationRuleMeta(BaseModel):
    total_transactions: int
    multi_aspect_transactions: int
    minimum_transactions: int
    sufficient_data: bool
    min_support: float
    min_confidence: float
    filters: MiningFilterSummary
    assumption: str


class AssociationRuleResponse(BaseModel):
    rules: list[AssociationRuleResult]
    meta: AssociationRuleMeta


class EntityClusterMember(BaseModel):
    entity_id: int
    entity_name: str
    platform: str
    total_reviews: int
    positive_ratio: float
    negative_ratio: float
    avg_confidence: float
    x_value: float
    y_value: float


class EntityClusterCentroid(BaseModel):
    positive_ratio: float
    negative_ratio: float
    avg_confidence: float
    total_reviews: float
    x_value: float
    y_value: float


class EntityClusterResult(BaseModel):
    cluster_id: int
    label: str
    entities: list[EntityClusterMember]
    centroid: EntityClusterCentroid


class EntityClusterMeta(BaseModel):
    algorithm: ClusterAlgorithm
    requested_k: int
    actual_clusters: int
    x_axis: MiningAxis
    y_axis: MiningAxis
    total_entities: int
    minimum_entities: int
    sufficient_data: bool
    filters: MiningFilterSummary
    assumption: str


class EntityClusterResponse(BaseModel):
    clusters: list[EntityClusterResult]
    meta: EntityClusterMeta
