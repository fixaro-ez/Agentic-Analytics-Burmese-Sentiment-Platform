from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import AuthUser, get_current_user
from ..models.mining import AssociationRuleResponse, EntityClusterResponse
from ..services.mining import (
    get_association_rule_analysis,
    get_association_rule_results,
    get_cluster_analysis,
    get_cluster_results,
)

router = APIRouter()


def _parse_entity_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    try:
        ids = [int(part) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="entity_ids must contain positive integers"
        ) from exc
    if not ids or any(entity_id <= 0 for entity_id in ids):
        raise HTTPException(
            status_code=422, detail="entity_ids must contain positive integers"
        )
    return list(dict.fromkeys(ids))


@router.get("/association-rules", response_model=AssociationRuleResponse)
async def get_association_rules(
    entity_ids: str | None = None,
    days: int | None = Query(default=None, ge=1, le=365),
    min_support: float = Query(default=0.05, ge=0, le=1),
    min_confidence: float = Query(default=0.2, ge=0, le=1),
    user: AuthUser = Depends(get_current_user),
):
    return await get_association_rule_analysis(
        entity_ids=_parse_entity_ids(entity_ids),
        days=days,
        min_support=min_support,
        min_confidence=min_confidence,
    )


@router.get("/clusters", response_model=EntityClusterResponse)
async def get_clusters(
    entity_ids: str | None = None,
    days: int | None = Query(default=None, ge=1, le=365),
    algorithm: Literal["kmeans", "hierarchical"] = "kmeans",
    k: int = Query(default=3, ge=2, le=6),
    x_axis: Literal[
        "positive_ratio", "negative_ratio", "avg_confidence", "total_reviews"
    ] = "positive_ratio",
    y_axis: Literal[
        "positive_ratio", "negative_ratio", "avg_confidence", "total_reviews"
    ] = "negative_ratio",
    user: AuthUser = Depends(get_current_user),
):
    try:
        return await get_cluster_analysis(
            entity_ids=_parse_entity_ids(entity_ids),
            days=days,
            algorithm=algorithm,
            k=k,
            x_axis=x_axis,
            y_axis=y_axis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/run")
async def run_mining(user: AuthUser = Depends(get_current_user)):
    return {
        "status": "completed",
        "rules": await get_association_rule_results(),
        "clusters": await get_cluster_results(),
    }
