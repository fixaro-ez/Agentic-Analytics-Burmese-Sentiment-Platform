from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse

from ..auth import AuthUser, get_current_user
from ..models.scraping import (
    CookieStatus,
    SavedScrapeEntity,
    SavedScrapeEntityWrite,
    ScrapeCancelResponse,
    ScrapeDetectResponse,
    ScrapeReadiness,
    ScrapeRequest,
    ScrapeRunHistory,
    ScrapeRunResponse,
    ScrapeRunStatus,
    ScrapeSchedule,
    ScrapeScheduleWrite,
)
from ..services.scraping import (
    ScrapeConflictError,
    ScrapeNotFoundError,
    ScrapePreflightError,
    cancel_scrape,
    check_facebook_cookies,
    create_saved_entity,
    create_schedule,
    delete_saved_entity,
    delete_schedule,
    detect_scrape_target,
    get_scrape_history,
    get_scrape_readiness,
    get_scrape_status,
    list_saved_entities,
    list_schedules,
    run_saved_entity,
    start_scrape,
    stream_scrape_events,
    update_saved_entity,
    upload_facebook_cookies,
)

router = APIRouter()
MAX_COOKIE_UPLOAD_BYTES = 1024 * 1024


@router.post("/run", response_model=ScrapeRunResponse)
async def trigger_scrape(
    body: ScrapeRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Queue a scrape and optionally save its reusable source configuration."""
    try:
        saved_entity = None
        if body.save_for_future:
            saved_entity = await create_saved_entity(
                SavedScrapeEntityWrite(
                    source=body.source,
                    source_url=body.url,
                    display_name=body.entity_name,
                    max_posts=body.max_posts,
                    headless=body.headless,
                    auto_pipeline=body.run_full_pipeline,
                ),
                user.user_id,
            )
        run_id = await start_scrape(
            source=body.source,
            url=body.url,
            entity_name=body.entity_name,
            max_posts=body.max_posts,
            headless=body.headless,
            user_id=user.user_id,
            run_full_pipeline=body.run_full_pipeline,
            saved_entity_id=saved_entity.id if saved_entity else None,
            trigger_kind="saved_entity" if saved_entity else "manual",
        )
    except ScrapePreflightError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScrapeConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ScrapeRunResponse(
        run_id=run_id,
        status="queued",
        message=f"{body.source.capitalize()} scrape queued for '{body.entity_name}'",
    )


@router.get("/status/{run_id}", response_model=ScrapeRunStatus)
async def scrape_status(
    run_id: str,
    user: AuthUser = Depends(get_current_user),
):
    result = await get_scrape_status(run_id, user.user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.get("/events/{run_id}")
async def scrape_events(
    run_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """Authenticated server-sent progress snapshots."""
    if await get_scrape_status(run_id, user.user_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_stream():
        async for payload in stream_scrape_events(run_id, user.user_id):
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cancel/{run_id}", response_model=ScrapeCancelResponse)
async def cancel_run(
    run_id: str,
    user: AuthUser = Depends(get_current_user),
):
    try:
        status = await cancel_scrape(run_id, user.user_id)
    except ScrapeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScrapeCancelResponse(
        run_id=run_id,
        status=status,
        message=(
            "Cancellation requested. The browser worker will stop at its next safe checkpoint."
            if status == "cancelling"
            else f"Run is already {status}."
        ),
    )


@router.get("/history", response_model=list[ScrapeRunHistory])
async def scrape_history(
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
):
    return await get_scrape_history(limit=limit, user_id=user.user_id)


@router.get("/detect", response_model=ScrapeDetectResponse)
async def detect_source(
    url: str = Query(min_length=1, max_length=2048),
    user: AuthUser = Depends(get_current_user),
):
    return detect_scrape_target(url)


@router.get("/entities", response_model=list[SavedScrapeEntity])
async def saved_entities(user: AuthUser = Depends(get_current_user)):
    return await list_saved_entities(user.user_id)


@router.post("/entities", response_model=SavedScrapeEntity, status_code=201)
async def save_entity(
    body: SavedScrapeEntityWrite,
    user: AuthUser = Depends(get_current_user),
):
    try:
        return await create_saved_entity(body, user.user_id)
    except ScrapeConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/entities/{entity_id}", response_model=SavedScrapeEntity)
async def edit_saved_entity(
    entity_id: str,
    body: SavedScrapeEntityWrite,
    user: AuthUser = Depends(get_current_user),
):
    try:
        return await update_saved_entity(entity_id, body, user.user_id)
    except ScrapeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/entities/{entity_id}", status_code=204)
async def remove_saved_entity(
    entity_id: str,
    user: AuthUser = Depends(get_current_user),
):
    if not await delete_saved_entity(entity_id, user.user_id):
        raise HTTPException(status_code=404, detail="Saved scrape target not found")
    return Response(status_code=204)


@router.post("/entities/{entity_id}/run", response_model=ScrapeRunResponse)
async def rescrape_saved_entity(
    entity_id: str,
    user: AuthUser = Depends(get_current_user),
):
    try:
        run_id = await run_saved_entity(entity_id, user.user_id)
    except ScrapeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScrapePreflightError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScrapeConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ScrapeRunResponse(
        run_id=run_id,
        status="queued",
        message="Saved target queued for re-scrape.",
    )


@router.get("/schedules", response_model=list[ScrapeSchedule])
async def scrape_schedules(user: AuthUser = Depends(get_current_user)):
    return await list_schedules(user.user_id)


@router.post("/schedules", response_model=ScrapeSchedule, status_code=201)
async def save_schedule(
    body: ScrapeScheduleWrite,
    user: AuthUser = Depends(get_current_user),
):
    try:
        return await create_schedule(body, user.user_id)
    except ScrapeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}", status_code=204)
async def remove_schedule(
    schedule_id: str,
    user: AuthUser = Depends(get_current_user),
):
    if not await delete_schedule(schedule_id, user.user_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return Response(status_code=204)


@router.get("/readiness", response_model=ScrapeReadiness)
async def scrape_readiness(
    source: str = Query(default="facebook", pattern="^(facebook|foodpanda)$"),
    user: AuthUser = Depends(get_current_user),
):
    return await get_scrape_readiness(source)


@router.get("/cookies", response_model=CookieStatus)
async def cookie_status(user: AuthUser = Depends(get_current_user)):
    return check_facebook_cookies()


@router.post("/cookies", response_model=CookieStatus)
async def upload_cookies(
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
):
    content = await file.read(MAX_COOKIE_UPLOAD_BYTES + 1)
    await file.close()
    if len(content) > MAX_COOKIE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="cookies.json must be 1 MB or smaller",
        )
    result = upload_facebook_cookies(content)
    if not result.valid:
        raise HTTPException(status_code=422, detail=result.message)
    return result
