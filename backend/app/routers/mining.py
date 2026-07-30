from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import AuthUser, get_current_user
from ..services.mining import get_association_rule_results, get_cluster_results

router = APIRouter()


@router.get("/association-rules")
async def get_association_rules(user: AuthUser = Depends(get_current_user)):
    return {"rules": await get_association_rule_results()}


@router.get("/clusters")
async def get_clusters(user: AuthUser = Depends(get_current_user)):
    return {"clusters": await get_cluster_results()}


@router.post("/run")
async def run_mining(user: AuthUser = Depends(get_current_user)):
    return {
        "status": "completed",
        "rules": await get_association_rule_results(),
        "clusters": await get_cluster_results(),
    }
