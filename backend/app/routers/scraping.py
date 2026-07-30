from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..auth import AuthUser, get_current_user
from ..models.scraping import (
    CookieStatus,
    ScrapeRequest,
    ScrapeRunHistory,
    ScrapeRunResponse,
    ScrapeRunStatus,
)
from ..services.scraping import (
    check_facebook_cookies,
    get_scrape_history,
    get_scrape_status,
    start_scrape,
    upload_facebook_cookies,
)

router = APIRouter()


@router.post("/run", response_model=ScrapeRunResponse)
async def trigger_scrape(
    body: ScrapeRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Start a new scrape job. Returns run_id immediately; poll /status for progress."""
    run_id = await start_scrape(
        source=body.source,
        url=body.url,
        entity_name=body.entity_name,
        max_posts=body.max_posts,
        headless=body.headless,
        user_id=user.user_id,
    )
    return ScrapeRunResponse(
        run_id=run_id,
        status="running",
        message=f"{body.source.capitalize()} scrape started for '{body.entity_name}'",
    )


@router.get("/status/{run_id}", response_model=ScrapeRunStatus)
async def scrape_status(
    run_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """Poll scrape progress by run_id."""
    result = await get_scrape_status(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.get("/history", response_model=list[ScrapeRunHistory])
async def scrape_history(
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
):
    """List recent scrape runs (newest first)."""
    return await get_scrape_history(limit=limit)


@router.get("/cookies", response_model=CookieStatus)
async def cookie_status(
    user: AuthUser = Depends(get_current_user),
):
    """Check if Facebook cookies.json exists and is valid."""
    return check_facebook_cookies()


@router.post("/cookies", response_model=CookieStatus)
async def upload_cookies(
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
):
    """Upload Facebook cookies.json file."""
    content = await file.read()
    return upload_facebook_cookies(content)
