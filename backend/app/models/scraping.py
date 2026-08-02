from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field, model_validator

FOODPANDA_RESTAURANT_PATH_RE = re.compile(
    r"^/(?:[a-z]{2}/)?restaurant/[a-z0-9]{4}/[^/]+(?:/reviews)?/?$",
    re.IGNORECASE,
)


def _validate_foodpanda_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    if not (
        hostname == "foodpanda.com.mm" or hostname.endswith(".foodpanda.com.mm")
    ):
        raise ValueError("Foodpanda scraping requires a foodpanda.com.mm URL")
    if not FOODPANDA_RESTAURANT_PATH_RE.fullmatch(parsed.path):
        raise ValueError(
            "Foodpanda URL must be a restaurant page in the form "
            "https://www.foodpanda.com.mm/restaurant/abcd/shop-name"
        )


# ---------- Request models ----------

class ScrapeRequest(BaseModel):
    """Body for POST /api/scraping/run — starts a new scrape job."""

    source: Literal["facebook", "foodpanda"]
    url: str = Field(min_length=1, max_length=2048)
    entity_name: str = Field(min_length=1, max_length=200)
    max_posts: int = Field(default=10, ge=1, le=200)
    headless: bool = True
    run_full_pipeline: bool = True
    save_for_future: bool = False

    @model_validator(mode="after")
    def validate_source_url(self) -> "ScrapeRequest":
        self.url = self.url.strip()
        self.entity_name = self.entity_name.strip()
        parsed = urlparse(self.url)
        hostname = (parsed.hostname or "").casefold()

        if parsed.scheme != "https" or not hostname:
            raise ValueError("URL must be a complete https:// address")
        if self.source == "facebook" and not (
            hostname == "facebook.com" or hostname.endswith(".facebook.com")
        ):
            raise ValueError("Facebook scraping requires a facebook.com URL")
        if self.source == "facebook":
            try:
                decoded_path = unquote(parsed.path)
            except UnicodeError as exc:
                raise ValueError("Facebook URL path is not valid URL encoding") from exc
            if any(character.isspace() for character in decoded_path):
                raise ValueError(
                    "Facebook page URL cannot contain spaces. Copy the exact page "
                    "address from Facebook, for example "
                    "https://www.facebook.com/LotteriaMyanmar"
                )
            if decoded_path.strip("/") == "" and not parsed.query:
                raise ValueError(
                    "Facebook URL must identify a page or post, not the Facebook home page"
                )
        if self.source == "foodpanda":
            _validate_foodpanda_url(self.url)
        return self


# ---------- Response models ----------

class ScrapeRunResponse(BaseModel):
    """Returned immediately when a scrape job starts."""

    run_id: str
    status: str
    message: str


class ScrapeRunStatus(BaseModel):
    """Polled via GET /api/scraping/status/{run_id} for progress."""

    run_id: str
    source: str
    entity_name: str
    url: str
    status: str
    started_at: str
    completed_at: str | None = None
    duration_seconds: float | None = None
    stats: dict | None = None
    error: str | None = None
    etl_run_id: str | None = None
    phase: str | None = None
    progress_percent: int | None = None
    cancellation_requested: bool = False
    saved_entity_id: str | None = None


class ScrapeRunHistory(BaseModel):
    """Single row in the scrape history list."""

    run_id: str
    run_type: str
    status: str
    started_at: str
    completed_at: str | None = None
    duration_seconds: float | None = None
    stats: dict | None = None
    error: str | None = None


class CookieStatus(BaseModel):
    """Facebook cookie file check result."""

    exists: bool
    valid: bool
    expires_at: str | None = None
    message: str


class ScrapeReadiness(BaseModel):
    """Preflight state required before a scrape can start."""

    source: Literal["facebook", "foodpanda"]
    ready: bool
    mongodb_ready: bool
    cookies_ready: bool | None = None
    pipeline_ready: bool | None = None
    postgres_ready: bool | None = None
    models_ready: bool | None = None
    pipeline_message: str | None = None
    message: str


class SavedScrapeEntityWrite(BaseModel):
    source: Literal["facebook", "foodpanda"]
    source_url: str = Field(min_length=1, max_length=2048)
    display_name: str = Field(min_length=1, max_length=200)
    dim_entity_id: int | None = Field(default=None, ge=1)
    max_posts: int = Field(default=10, ge=1, le=200)
    headless: bool = True
    auto_pipeline: bool = True

    @model_validator(mode="after")
    def validate_source_url(self) -> "SavedScrapeEntityWrite":
        self.source_url = self.source_url.strip()
        self.display_name = self.display_name.strip()
        if self.source == "foodpanda":
            _validate_foodpanda_url(self.source_url)
        return self

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "SavedScrapeEntityWrite":
        validated = ScrapeRequest(
            source=self.source,
            url=self.source_url,
            entity_name=self.display_name,
            max_posts=self.max_posts,
            headless=self.headless,
            run_full_pipeline=self.auto_pipeline,
        )
        self.source_url = validated.url
        self.display_name = validated.entity_name
        return self


class SavedScrapeEntity(BaseModel):
    id: str
    dim_entity_id: int | None = None
    source: Literal["facebook", "foodpanda"]
    source_url: str
    display_name: str
    max_posts: int
    headless: bool
    auto_pipeline: bool
    created_at: str
    updated_at: str
    last_scraped_at: str | None = None
    last_scrape_status: str | None = None
    last_scrape_error: str | None = None


def _validate_timezone_name(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 100 or "/" not in value:
        raise ValueError("timezone must be an IANA name such as Asia/Yangon")
    return value


class ScrapeScheduleWrite(BaseModel):
    entity_id: str
    cron_expression: str = Field(min_length=5, max_length=100)
    timezone: str = "Asia/Yangon"
    active: bool = True

    @model_validator(mode="after")
    def normalize_schedule(self) -> "ScrapeScheduleWrite":
        self.entity_id = self.entity_id.strip()
        self.cron_expression = " ".join(self.cron_expression.split())
        self.timezone = _validate_timezone_name(self.timezone)
        if len(self.cron_expression.split()) != 5:
            raise ValueError("cron_expression must have five fields")
        return self


class ScrapeSchedule(BaseModel):
    id: str
    entity_id: str
    cron_expression: str
    timezone: str
    active: bool
    created_at: str
    updated_at: str
    next_run: str | None = None
    last_run_at: str | None = None
    display_name: str | None = None
    source: str | None = None


class ScrapeDetectResponse(BaseModel):
    source: Literal["facebook", "foodpanda"] | None
    entity_name: str | None
    supported: bool
    message: str


class ScrapeCancelResponse(BaseModel):
    run_id: str
    status: str
    message: str
