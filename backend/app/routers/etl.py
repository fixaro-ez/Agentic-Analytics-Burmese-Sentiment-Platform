from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import AuthUser, get_current_user
from ..models.etl import (
    ETLAbsaRequest,
    ETLCleanRequest,
    ETLRunHistory,
    ETLRunRequest,
    ETLRunResponse,
    ETLHealthResponse,
    ETLStatusResponse,
)
from ..services.etl import (
    get_health,
    get_history,
    get_status,
    run_absa_etl,
    run_clean_etl,
    run_export_etl,
    run_full_etl,
)

router = APIRouter()


@router.post("/run", response_model=ETLRunResponse)
async def trigger_full_etl(
    body: ETLRunRequest = ETLRunRequest(),
    user: AuthUser = Depends(get_current_user),
):
    run_id = await run_full_etl(
        reprocess=body.reprocess,
        threshold=body.threshold,
        user_id=user.user_id,
        target=body.target,
    )
    return ETLRunResponse(
        run_id=run_id,
        status="running",
        message="Full ETL pipeline started (clean → ABSA → export)",
    )


@router.post("/clean", response_model=ETLRunResponse)
async def trigger_clean(
    body: ETLCleanRequest = ETLCleanRequest(),
    user: AuthUser = Depends(get_current_user),
):
    run_id = await run_clean_etl(
        collection=body.collection,
        reprocess=body.reprocess,
        user_id=user.user_id,
    )
    return ETLRunResponse(
        run_id=run_id,
        status="running",
        message=f"Text cleaning started for collection: {body.collection}",
    )


@router.post("/absa", response_model=ETLRunResponse)
async def trigger_absa(
    body: ETLAbsaRequest = ETLAbsaRequest(),
    user: AuthUser = Depends(get_current_user),
):
    run_id = await run_absa_etl(
        pipeline=body.pipeline,
        reprocess=body.reprocess,
        threshold=body.threshold,
        user_id=user.user_id,
    )
    return ETLRunResponse(
        run_id=run_id,
        status="running",
        message=f"ABSA inference started for pipeline: {body.pipeline}",
    )


@router.post("/export", response_model=ETLRunResponse)
async def trigger_export(
    user: AuthUser = Depends(get_current_user),
):
    run_id = await run_export_etl(user_id=user.user_id)
    return ETLRunResponse(
        run_id=run_id,
        status="running",
        message="PostgreSQL export started",
    )


@router.get("/status", response_model=ETLStatusResponse)
async def etl_status(user: AuthUser = Depends(get_current_user)):
    return await get_status()


@router.get("/health", response_model=ETLHealthResponse)
async def etl_health(user: AuthUser = Depends(get_current_user)):
    """Read-only, fault-tolerant pipeline health snapshot."""
    return await get_health()


@router.get("/history", response_model=list[ETLRunHistory])
async def etl_history(
    limit: int = Query(default=10, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
):
    return await get_history(limit=limit)
