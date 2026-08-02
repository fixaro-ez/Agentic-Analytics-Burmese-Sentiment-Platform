from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ETLRunRequest(BaseModel):
    reprocess: bool = False
    threshold: float = 0.5
    target: Literal["contents", "feedbacks", "both"] = "both"


class ETLCleanRequest(BaseModel):
    collection: Literal["contents", "feedbacks", "both"] = "both"
    reprocess: bool = False


class ETLAbsaRequest(BaseModel):
    pipeline: Literal["contents", "feedbacks", "both"] = "both"
    reprocess: bool = False
    threshold: float = 0.5


class ETLRunResponse(BaseModel):
    run_id: str
    status: str
    message: str


class MongoDBStatus(BaseModel):
    contents_raw: int
    contents_cleaned: int
    contents_absa: int
    feedbacks_raw: int
    feedbacks_cleaned: int
    feedbacks_absa: int


class PostgreSQLStatus(BaseModel):
    dim_entities: int
    fact_social_posts: int
    fact_review_absa_results: int


class ETLStatusResponse(BaseModel):
    mongodb: MongoDBStatus
    postgresql: PostgreSQLStatus


class ETLRunHistory(BaseModel):
    run_id: str
    run_type: str
    status: str
    started_at: str
    completed_at: str | None = None
    duration_seconds: float | None = None
    stats: dict | None = None
    error: str | None = None


PipelineStatus = Literal["active", "healthy", "idle", "stale", "error", "unavailable"]


class PipelineNodeHealth(BaseModel):
    id: Literal["scraper", "mongodb", "nlp", "postgresql"]
    label: str
    status: PipelineStatus
    metrics: dict[str, Any]
    detail: str
    last_activity_at: str | None = None
    error: str | None = None


class PostgresLoadStatus(BaseModel):
    table: str
    row_count: int | None = None
    last_loaded_at: str | None = None
    rows_loaded: int | None = None
    status: PipelineStatus


class ETLHealthResponse(BaseModel):
    generated_at: str
    overall_status: PipelineStatus
    stale_after_minutes: int
    nodes: list[PipelineNodeHealth]
    loads: list[PostgresLoadStatus]
    latest_run: ETLRunHistory | None = None
