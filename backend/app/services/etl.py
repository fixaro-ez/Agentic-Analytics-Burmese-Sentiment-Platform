from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from ..config import settings
from ..database import get_pool
from ..models.etl import (
    ETLHealthResponse,
    ETLRunHistory,
    ETLStatusResponse,
    MongoDBStatus,
    PipelineNodeHealth,
    PostgresLoadStatus,
    PostgreSQLStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

MONGO_URI = settings.MONGO_URI
DB_NAME = "feedback_analytics"

CLEANED_FEEDBACKS = "cleaned_feedbacks"
CLEANED_CONTENTS = "cleaned_contents"
OUTPUT_FEEDBACKS = "absa_processed_feedbacks"
OUTPUT_CONTENTS = "absa_processed_contents"
CONTENTS_COLLECTION = "contents"
_active_etl_tasks: set[asyncio.Task[None]] = set()
logger = logging.getLogger(__name__)


def _start_tracked_task(coro) -> None:
    """Keep background ETL work alive until it reaches a terminal state."""
    task = asyncio.create_task(coro)
    _active_etl_tasks.add(task)
    task.add_done_callback(_active_etl_tasks.discard)
FEEDBACKS_COLLECTION = "feedbacks"

_aspect_tokenizer = None
_aspect_model = None
_sentiment_tokenizer = None
_sentiment_model = None
_device: str = "cpu"
_dtype: Any = None
_batch_size: int = 8


def _get_mongo_client() -> MongoClient:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client


async def _ensure_etl_runs_table() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS etl_runs ("
            "  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  run_type VARCHAR(20) NOT NULL,"
            "  status VARCHAR(20) NOT NULL DEFAULT 'running',"
            "  started_at TIMESTAMPTZ DEFAULT NOW(),"
            "  completed_at TIMESTAMPTZ,"
            "  duration_seconds FLOAT,"
            "  stats JSONB,"
            "  error TEXT,"
            "  triggered_by UUID"
            ")"
        )


async def get_status() -> ETLStatusResponse:
    client = _get_mongo_client()
    try:
        db = client[DB_NAME]

        def _mongo_counts() -> dict[str, int]:
            return {
                "contents_raw": db[CONTENTS_COLLECTION].count_documents({}),
                "contents_cleaned": db[CLEANED_CONTENTS].count_documents({}),
                "contents_absa": db[OUTPUT_CONTENTS].count_documents({}),
                "feedbacks_raw": db[FEEDBACKS_COLLECTION].count_documents({}),
                "feedbacks_cleaned": db[CLEANED_FEEDBACKS].count_documents({}),
                "feedbacks_absa": db[OUTPUT_FEEDBACKS].count_documents({}),
            }

        mongo = await asyncio.to_thread(_mongo_counts)
    finally:
        client.close()

    pool = await get_pool()
    async with pool.acquire() as conn:
        pg = {
            "dim_entities": await conn.fetchval("SELECT COUNT(*)::int FROM dim_entities"),
            "fact_social_posts": await conn.fetchval("SELECT COUNT(*)::int FROM fact_social_posts"),
            "fact_review_absa_results": await conn.fetchval("SELECT COUNT(*)::int FROM fact_review_absa_results"),
        }

    return ETLStatusResponse(
        mongodb=MongoDBStatus(**mongo),
        postgresql=PostgreSQLStatus(**pg),
    )


def _decoded_stats(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _row_history(row: Any) -> ETLRunHistory:
    return ETLRunHistory(
        run_id=row["run_id"],
        run_type=row["run_type"],
        status=row["status"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        duration_seconds=row["duration_seconds"],
        stats=_decoded_stats(row["stats"]) or None,
        error=row["error"],
    )


async def get_health(stale_after_minutes: int = 30) -> ETLHealthResponse:
    """Return a fault-tolerant snapshot for the read-only pipeline dialog."""
    generated_at = datetime.now(timezone.utc)
    mongo_counts: dict[str, int] | None = None
    mongo_error: str | None = None

    def _read_mongo() -> dict[str, int]:
        from burmese_absa.clean_feedbacks import (
            CONTENT_SOURCE_FIELDS,
            FEEDBACK_SOURCE_FIELDS,
            source_fingerprint,
        )

        client = _get_mongo_client()
        try:
            db = client[DB_NAME]
            counts = {
                "contents_raw": db[CONTENTS_COLLECTION].count_documents({}),
                "contents_cleaned": db[CLEANED_CONTENTS].count_documents({}),
                "contents_absa": db[OUTPUT_CONTENTS].count_documents({}),
                "feedbacks_raw": db[FEEDBACKS_COLLECTION].count_documents({}),
                "feedbacks_cleaned": db[CLEANED_FEEDBACKS].count_documents({}),
                "feedbacks_absa": db[OUTPUT_FEEDBACKS].count_documents({}),
            }
            cleaned_content_fingerprints = {
                doc["_id"]: doc.get("source_fingerprint")
                for doc in db[CLEANED_CONTENTS].find(
                    {}, {"_id": 1, "source_fingerprint": 1}
                )
            }
            cleaned_feedback_fingerprints = {
                doc["_id"]: doc.get("source_fingerprint")
                for doc in db[CLEANED_FEEDBACKS].find(
                    {}, {"_id": 1, "source_fingerprint": 1}
                )
            }
            content_projection = {
                "_id": 1,
                **{field: 1 for field in CONTENT_SOURCE_FIELDS},
            }
            feedback_projection = {
                "_id": 1,
                **{field: 1 for field in FEEDBACK_SOURCE_FIELDS},
            }
            counts["pending_cleaning"] = sum(
                cleaned_content_fingerprints.get(doc["_id"])
                != source_fingerprint(doc, CONTENT_SOURCE_FIELDS)
                for doc in db[CONTENTS_COLLECTION].find(
                    {}, content_projection
                )
            ) + sum(
                cleaned_feedback_fingerprints.get(doc["_id"])
                != source_fingerprint(doc, FEEDBACK_SOURCE_FIELDS)
                for doc in db[FEEDBACKS_COLLECTION].find(
                    {}, feedback_projection
                )
            )

            processed_content_fingerprints = {
                doc["_id"]: doc.get("source_fingerprint")
                for doc in db[OUTPUT_CONTENTS].find(
                    {}, {"_id": 1, "source_fingerprint": 1}
                )
            }
            processed_feedback_fingerprints = {
                doc["_id"]: doc.get("source_fingerprint")
                for doc in db[OUTPUT_FEEDBACKS].find(
                    {}, {"_id": 1, "source_fingerprint": 1}
                )
            }
            counts["pending_nlp"] = sum(
                processed_content_fingerprints.get(doc["_id"])
                != doc.get("source_fingerprint")
                for doc in db[CLEANED_CONTENTS].find(
                    {
                        "platform": "facebook",
                        "cleaning_status": "clean",
                        "cleaned_text": {"$exists": True, "$ne": ""},
                    },
                    {"_id": 1, "source_fingerprint": 1},
                )
            ) + sum(
                processed_feedback_fingerprints.get(doc["_id"])
                != doc.get("source_fingerprint")
                for doc in db[CLEANED_FEEDBACKS].find(
                    {
                        "cleaning_status": "clean",
                        "cleaned_text": {"$exists": True, "$ne": ""},
                    },
                    {"_id": 1, "source_fingerprint": 1},
                )
            )
            return counts
        finally:
            client.close()

    try:
        mongo_counts = await asyncio.to_thread(_read_mongo)
    except Exception as exc:
        mongo_error = _format_service_error(exc)

    pg_counts: dict[str, int] | None = None
    pg_error: str | None = None
    run_rows: list[Any] = []
    try:
        await _ensure_etl_runs_table()
        pool = await get_pool()
        async with pool.acquire() as conn:
            pg_counts = {
                "dim_entities": await conn.fetchval(
                    "SELECT COUNT(*)::int FROM dim_entities"
                ),
                "fact_social_posts": await conn.fetchval(
                    "SELECT COUNT(*)::int FROM fact_social_posts"
                ),
                "fact_review_absa_results": await conn.fetchval(
                    "SELECT COUNT(*)::int FROM fact_review_absa_results"
                ),
                "fact_review_documents": await conn.fetchval(
                    "SELECT COUNT(DISTINCT feedback_id)::int "
                    "FROM fact_review_absa_results"
                ),
            }
            run_rows = await conn.fetch(
                "SELECT run_id::text, run_type, status, "
                "started_at::text, completed_at::text, duration_seconds, stats, error "
                "FROM etl_runs ORDER BY started_at DESC LIMIT 100"
            )
    except Exception as exc:
        pg_error = _format_service_error(exc)

    histories = [_row_history(row) for row in run_rows]
    latest_run = histories[0] if histories else None

    def _latest(types: set[str]) -> ETLRunHistory | None:
        return next((run for run in histories if run.run_type in types), None)

    scraper_run = next(
        (run for run in histories if run.run_type.startswith("scrape_")), None
    )
    nlp_run = _latest({"clean", "absa", "full"})
    export_run = _latest({"export", "full"})
    running_scrapes = sum(
        1
        for run in histories
        if run.run_type.startswith("scrape_")
        and run.status in {"queued", "running", "cancelling"}
    )

    def _age_minutes(run: ETLRunHistory | None) -> float | None:
        if run is None:
            return None
        raw = run.completed_at or run.started_at
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return max(0, (generated_at - value.astimezone(timezone.utc)).total_seconds() / 60)
        except (TypeError, ValueError):
            return None

    def _run_status(
        run: ETLRunHistory | None, *, active: bool = False
    ) -> str:
        if active:
            return "active"
        if run is None:
            return "idle"
        if run.status == "failed":
            return "error"
        age = _age_minutes(run)
        if age is not None and age > stale_after_minutes:
            return "stale"
        return "healthy" if run.status in {"completed", "partial"} else "active"

    scraper_status = _run_status(scraper_run, active=running_scrapes > 0)
    mongo_status = "unavailable" if mongo_error else "healthy"
    nlp_active = bool(nlp_run and nlp_run.status == "running")
    nlp_status = (
        "unavailable" if mongo_error else _run_status(nlp_run, active=nlp_active)
    )
    pg_status = (
        "unavailable"
        if pg_error
        else _run_status(
            export_run,
            active=bool(export_run and export_run.status == "running"),
        )
    )

    mongo_metrics = mongo_counts or {}
    pending_clean = (
        mongo_counts.get("pending_cleaning") if mongo_counts else None
    )
    pending_nlp = mongo_counts.get("pending_nlp") if mongo_counts else None
    pending_postgres = None
    if mongo_counts and pg_counts:
        pending_postgres = max(
            0,
            mongo_counts["contents_absa"] - pg_counts["fact_social_posts"],
        ) + max(
            0,
            mongo_counts["feedbacks_absa"]
            - pg_counts["fact_review_documents"],
        )
    if (
        nlp_status not in {"active", "error", "unavailable"}
        and ((pending_clean or 0) > 0 or (pending_nlp or 0) > 0)
    ):
        nlp_status = "stale"
    if (
        pg_status not in {"active", "error", "unavailable"}
        and (pending_postgres or 0) > 0
    ):
        pg_status = "stale"

    nodes = [
        PipelineNodeHealth(
            id="scraper",
            label="Scrapers",
            status=scraper_status,
            metrics={
                "running_jobs": running_scrapes,
                "latest_source": (
                    scraper_run.run_type.replace("scrape_", "")
                    if scraper_run
                    else None
                ),
                "latest_status": scraper_run.status if scraper_run else None,
            },
            detail=(
                "Facebook and Foodpanda collection workers."
                if scraper_run
                else "No scrape run has been recorded yet."
            ),
            last_activity_at=(
                scraper_run.completed_at or scraper_run.started_at
                if scraper_run
                else None
            ),
            error=scraper_run.error if scraper_run and scraper_run.status == "failed" else None,
        ),
        PipelineNodeHealth(
            id="mongodb",
            label="MongoDB",
            status=mongo_status,
            metrics={**mongo_metrics, "pending_cleaning": pending_clean},
            detail="Raw and cleaned source documents.",
            error=mongo_error,
        ),
        PipelineNodeHealth(
            id="nlp",
            label="XLM-R NLP",
            status=nlp_status,
            metrics={
                "pending_documents": pending_nlp,
                "processed_contents": (
                    mongo_counts["contents_absa"] if mongo_counts else None
                ),
                "processed_feedbacks": (
                    mongo_counts["feedbacks_absa"] if mongo_counts else None
                ),
            },
            detail="Burmese-aware cleaning, aspect extraction, and sentiment.",
            last_activity_at=(
                nlp_run.completed_at or nlp_run.started_at if nlp_run else None
            ),
            error=nlp_run.error if nlp_run and nlp_run.status == "failed" else mongo_error,
        ),
        PipelineNodeHealth(
            id="postgresql",
            label="Postgres DWH",
            status=pg_status,
            metrics={
                **(pg_counts or {}),
                "pending_documents": pending_postgres,
            },
            detail="Read-optimized entity, post, and review facts.",
            last_activity_at=(
                export_run.completed_at or export_run.started_at
                if export_run
                else None
            ),
            error=pg_error or (
                export_run.error
                if export_run and export_run.status == "failed"
                else None
            ),
        ),
    ]

    export_stats: dict[str, Any] = {}
    if export_run and export_run.stats:
        export_stats = _decoded_stats(export_run.stats.get("export", export_run.stats))
    load_keys = {
        "dim_entities": "entities",
        "fact_social_posts": "posts",
        "fact_review_absa_results": "reviews",
    }
    loads = [
        PostgresLoadStatus(
            table=table,
            row_count=(pg_counts or {}).get(table),
            last_loaded_at=export_run.completed_at if export_run else None,
            rows_loaded=(
                int(export_stats[key])
                if isinstance(export_stats.get(key), (int, float))
                else None
            ),
            status=pg_status,
        )
        for table, key in load_keys.items()
    ]

    priority = {
        "unavailable": 5,
        "error": 4,
        "stale": 3,
        "active": 2,
        "idle": 1,
        "healthy": 0,
    }
    overall_status = max(
        (node.status for node in nodes), key=lambda status: priority[status]
    )
    return ETLHealthResponse(
        generated_at=generated_at.isoformat(),
        overall_status=overall_status,
        stale_after_minutes=stale_after_minutes,
        nodes=nodes,
        loads=loads,
        latest_run=latest_run,
    )


def _format_service_error(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or type(exc).__name__


async def get_history(limit: int = 10) -> list[ETLRunHistory]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT run_id::text, run_type, status, "
            "  started_at::text, completed_at::text, duration_seconds, "
            "  stats, error "
            "FROM etl_runs ORDER BY started_at DESC LIMIT $1",
            limit,
        )
    return [_row_history(row) for row in rows]


async def _create_run(run_type: str, user_id: str | None = None) -> str:
    await _ensure_etl_runs_table()
    pool = await get_pool()
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            "INSERT INTO etl_runs (run_type, triggered_by) VALUES ($1, $2::uuid) "
            "RETURNING run_id::text",
            run_type,
            user_id,
        )
    return run_id


async def _finish_run(
    run_id: str, status: str, stats: dict | None = None, error: str | None = None
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE etl_runs SET status = $2, completed_at = NOW(), "
            "  duration_seconds = EXTRACT(EPOCH FROM NOW() - started_at), "
            "  stats = $3::jsonb, error = $4 "
            "WHERE run_id::text = $1",
            run_id,
            status,
            json.dumps(stats) if stats else None,
            error,
        )


def _run_clean_sync(collection: str, reprocess: bool) -> dict[str, Any]:
    from burmese_absa.clean_feedbacks import (
        get_db,
        get_unprocessed_ids,
        process_contents,
        process_feedbacks,
        CONTENTS_COLLECTION as CC,
        FEEDBACKS_COLLECTION as FC,
        CLEANED_CONTENTS_COLLECTION as CLC,
        CLEANED_FEEDBACKS_COLLECTION as CLF,
    )

    db = get_db(MONGO_URI)
    try:
        total_stats: dict[str, Any] = {
            "processed": 0,
            "clean": 0,
            "filtered": 0,
            "empty": 0,
        }

        if reprocess:
            if collection in ("contents", "both"):
                db[CLC].drop()
            if collection in ("feedbacks", "both"):
                db[CLF].drop()

        if collection in ("contents", "both"):
            unprocessed = get_unprocessed_ids(CC, CLC, db)
            if unprocessed:
                stats = process_contents(unprocessed, db)
                for key in total_stats:
                    total_stats[key] += stats.get(key, 0)

        if collection in ("feedbacks", "both"):
            unprocessed = get_unprocessed_ids(FC, CLF, db)
            if unprocessed:
                stats = process_feedbacks(unprocessed, db)
                for key in total_stats:
                    total_stats[key] += stats.get(key, 0)

        return total_stats
    finally:
        db.client.close()


def _run_absa_sync(
    pipeline: str, reprocess: bool, threshold: float
) -> dict[str, Any]:
    global _aspect_tokenizer, _aspect_model
    global _sentiment_tokenizer, _sentiment_model
    global _device, _dtype, _batch_size

    from nlp.run_absa_pipeline import (
        get_db,
        detect_device,
        get_pending_content_ids,
        get_pending_feedback_ids,
        remove_ineligible_outputs,
        _resolve_model_path,
        run_feedbacks_pipeline,
        run_contents_pipeline,
        ASPECT_MODEL_FOLDER,
        SENTIMENT_MODEL_FOLDER,
        ASPECT_MODEL_ID,
        SENTIMENT_MODEL_ID,
        DEFAULT_MODELS_DIR,
    )
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    client, db = get_db(MONGO_URI)
    try:
        if reprocess:
            if pipeline in ("feedbacks", "both"):
                db[OUTPUT_FEEDBACKS].drop()
            if pipeline in ("contents", "both"):
                db[OUTPUT_CONTENTS].drop()

        removed_feedbacks = (
            remove_ineligible_outputs(db, "feedbacks")
            if pipeline in ("feedbacks", "both")
            else 0
        )
        removed_contents = (
            remove_ineligible_outputs(db, "contents")
            if pipeline in ("contents", "both")
            else 0
        )
        pending_feedbacks = (
            get_pending_feedback_ids(db, threshold)
            if pipeline in ("feedbacks", "both")
            else set()
        )
        pending_contents = (
            get_pending_content_ids(db, threshold)
            if pipeline in ("contents", "both")
            else set()
        )
        stats: dict[str, Any] = {}

        if not pending_feedbacks and not pending_contents:
            if pipeline in ("feedbacks", "both"):
                stats["feedbacks"] = {
                    "processed": 0,
                    "written": 0,
                    "skipped": 0,
                    "zero_aspect": 0,
                    "removed": removed_feedbacks,
                }
            if pipeline in ("contents", "both"):
                stats["contents"] = {
                    "processed": 0,
                    "written": 0,
                    "skipped": 0,
                    "removed": removed_contents,
                }
            return stats

        if _aspect_model is None:
            _device, _dtype, _batch_size = detect_device()
            models_dir = (
                DEFAULT_MODELS_DIR if DEFAULT_MODELS_DIR.exists() else None
            )
            aspect_source = _resolve_model_path(
                models_dir, ASPECT_MODEL_FOLDER, ASPECT_MODEL_ID
            )
            _aspect_tokenizer = AutoTokenizer.from_pretrained(aspect_source)
            _aspect_model = AutoModelForSequenceClassification.from_pretrained(
                aspect_source, dtype=_dtype
            ).to(_device)
            _aspect_model.eval()

        if _sentiment_model is None and pending_feedbacks:
            models_dir = (
                DEFAULT_MODELS_DIR if DEFAULT_MODELS_DIR.exists() else None
            )
            sentiment_source = _resolve_model_path(
                models_dir, SENTIMENT_MODEL_FOLDER, SENTIMENT_MODEL_ID
            )
            _sentiment_tokenizer = AutoTokenizer.from_pretrained(
                sentiment_source
            )
            _sentiment_model = (
                AutoModelForSequenceClassification.from_pretrained(
                    sentiment_source, dtype=_dtype
                ).to(_device)
            )
            _sentiment_model.eval()

        if pipeline in ("feedbacks", "both") and pending_feedbacks:
            fb_stats = run_feedbacks_pipeline(
                db,
                _aspect_tokenizer, _aspect_model,
                _sentiment_tokenizer, _sentiment_model,
                _device, _dtype, _batch_size, threshold,
            )
            fb_stats["removed"] = removed_feedbacks
            stats["feedbacks"] = fb_stats
        elif pipeline in ("feedbacks", "both"):
            stats["feedbacks"] = {
                "processed": 0,
                "written": 0,
                "skipped": 0,
                "zero_aspect": 0,
                "removed": removed_feedbacks,
            }

        if pipeline in ("contents", "both") and pending_contents:
            ct_stats = run_contents_pipeline(
                db,
                _aspect_tokenizer, _aspect_model,
                _device, _dtype, _batch_size, threshold,
            )
            ct_stats["removed"] = removed_contents
            stats["contents"] = ct_stats
        elif pipeline in ("contents", "both"):
            stats["contents"] = {
                "processed": 0,
                "written": 0,
                "skipped": 0,
                "removed": removed_contents,
            }

    finally:
        client.close()

    return stats


async def _export_to_postgres() -> dict[str, int]:
    from .brands import ensure_brand_schema

    await ensure_brand_schema()
    client = _get_mongo_client()
    try:
        db = client[DB_NAME]

        def _normalize_name(name: str) -> str:
            return re.sub(r'\s+', ' ', name.strip())

        def _read_mongo() -> tuple[list[dict], list[dict], set[tuple[str, str]]]:
            entities: set[tuple[str, str]] = set()
            for col in [OUTPUT_FEEDBACKS, OUTPUT_CONTENTS]:
                for doc in db[col].find({}, {"entity_name": 1, "platform": 1}):
                    name = _normalize_name(doc.get("entity_name", ""))
                    platform = doc.get("platform", "")
                    if name and platform:
                        entities.add((name, platform))

            contents = list(db[OUTPUT_CONTENTS].find({}))
            feedbacks = list(db[OUTPUT_FEEDBACKS].find({}))
            return contents, feedbacks, entities

        contents, feedbacks, entities = await asyncio.to_thread(_read_mongo)
    finally:
        client.close()

    pool = await get_pool()
    result: dict[str, int] = {
        "entities": 0,
        "posts": 0,
        "reviews": 0,
        "posts_deleted": 0,
        "reviews_deleted": 0,
    }

    def _affected_rows(command_tag: str) -> int:
        try:
            return int(command_tag.rsplit(" ", 1)[-1])
        except (TypeError, ValueError):
            return 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            for name, platform in entities:
                await conn.execute(
                    "INSERT INTO dim_entities (entity_name, platform) "
                    "VALUES ($1, $2) "
                    "ON CONFLICT (entity_name, platform) DO NOTHING",
                    name, platform,
                )
            result["entities"] = len(entities)

            entity_cache: dict[tuple[str, str], int | None] = {}

            async def _get_entity_id(name: str, platform: str) -> int | None:
                norm_name = _normalize_name(name)
                key = (norm_name, platform)
                if key not in entity_cache:
                    entity_cache[key] = await conn.fetchval(
                        "SELECT entity_id FROM dim_entities "
                        "WHERE entity_name = $1 AND platform = $2",
                        norm_name, platform,
                    )
                return entity_cache[key]

            source_post_ids = [str(doc["_id"]) for doc in contents]
            if source_post_ids:
                deleted = await conn.execute(
                    "DELETE FROM fact_social_posts "
                    "WHERE NOT (post_id = ANY($1::text[]))",
                    source_post_ids,
                )
            else:
                deleted = await conn.execute("DELETE FROM fact_social_posts")
            result["posts_deleted"] = _affected_rows(deleted)

            for doc in contents:
                eid = await _get_entity_id(
                    doc.get("entity_name", ""), doc.get("platform", "")
                )
                if eid is None:
                    continue
                aspect_conf = (
                    json.dumps(doc.get("aspect_probabilities"))
                    if doc.get("aspect_probabilities")
                    else None
                )
                await conn.execute(
                    "INSERT INTO fact_social_posts ("
                    "  post_id, entity_id, post_timestamp, post_text,"
                    "  promoted_aspects, aspect_confidence,"
                    "  total_reactions, like_count, love_count, haha_count,"
                    "  sad_count, angry_count, care_count, wow_count,"
                    "  shares_count, comments_count,"
                    "  positivity_ratio, negativity_ratio"
                    ") VALUES ("
                    "  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18"
                    ") ON CONFLICT (post_id) DO UPDATE SET "
                    "  entity_id=EXCLUDED.entity_id, post_timestamp=EXCLUDED.post_timestamp,"
                    "  post_text=EXCLUDED.post_text, promoted_aspects=EXCLUDED.promoted_aspects,"
                    "  aspect_confidence=EXCLUDED.aspect_confidence,"
                    "  total_reactions=EXCLUDED.total_reactions,"
                    "  like_count=EXCLUDED.like_count, love_count=EXCLUDED.love_count,"
                    "  haha_count=EXCLUDED.haha_count, sad_count=EXCLUDED.sad_count,"
                    "  angry_count=EXCLUDED.angry_count, care_count=EXCLUDED.care_count,"
                    "  wow_count=EXCLUDED.wow_count,"
                    "  shares_count=EXCLUDED.shares_count, comments_count=EXCLUDED.comments_count,"
                    "  positivity_ratio=EXCLUDED.positivity_ratio,"
                    "  negativity_ratio=EXCLUDED.negativity_ratio",
                    doc["_id"], eid, doc.get("post_timestamp"),
                    doc.get("post_text"), doc.get("promoted_aspects"),
                    aspect_conf,
                    doc.get("total_reactions"), doc.get("like_count"),
                    doc.get("love_count"), doc.get("haha_count"),
                    doc.get("sad_count"), doc.get("angry_count"),
                    doc.get("care_count"), doc.get("wow_count"),
                    doc.get("shares_count"),
                    doc.get("comments_count"), doc.get("positivity_ratio"),
                    doc.get("negativity_ratio"),
                )
                result["posts"] += 1

            feedback_ids = [
                str(doc.get("feedback_id", doc["_id"])) for doc in feedbacks
            ]
            if feedback_ids:
                deleted = await conn.execute(
                    "DELETE FROM fact_review_absa_results "
                    "WHERE NOT (feedback_id = ANY($1::text[]))",
                    feedback_ids,
                )
            else:
                deleted = await conn.execute(
                    "DELETE FROM fact_review_absa_results"
                )
            result["reviews_deleted"] = _affected_rows(deleted)

            if feedbacks:
                await conn.execute(
                    "DELETE FROM fact_review_absa_results WHERE feedback_id = ANY($1::text[])",
                    feedback_ids,
                )

                for doc in feedbacks:
                    eid = await _get_entity_id(
                        doc.get("entity_name", ""), doc.get("platform", "")
                    )
                    if eid is None:
                        continue
                    feedback_id = doc.get("feedback_id", doc["_id"])
                    feedback_ts = doc.get("feedback_timestamp")
                    raw_text = doc.get("raw_text")
                    aspect_sentiments = doc.get("aspect_sentiments", [])

                    if not aspect_sentiments:
                        await conn.execute(
                            "INSERT INTO fact_review_absa_results "
                            "  (feedback_id, entity_id, feedback_timestamp, raw_text, "
                            "   aspect_category, sentiment_label, confidence_score) "
                            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                            feedback_id, eid, feedback_ts, raw_text,
                            "no_aspect", None, None,
                        )
                        result["reviews"] += 1
                    else:
                        for item in aspect_sentiments:
                            await conn.execute(
                                "INSERT INTO fact_review_absa_results "
                                "  (feedback_id, entity_id, feedback_timestamp, raw_text, "
                                "   aspect_category, sentiment_label, confidence_score) "
                                "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                                feedback_id, eid, feedback_ts, raw_text,
                                item.get("aspect"), item.get("sentiment"),
                                item.get("confidence"),
                            )
                            result["reviews"] += 1

    return result


async def _validate_pipeline_sync(
    target: str, threshold: float
) -> dict[str, int]:
    """Prove that each requested stage has no remaining eligible backlog."""
    from burmese_absa.clean_feedbacks import (
        CLEANED_CONTENTS_COLLECTION,
        CLEANED_FEEDBACKS_COLLECTION,
        CONTENTS_COLLECTION,
        FEEDBACKS_COLLECTION,
        get_unprocessed_ids as get_unclean_ids,
    )
    from nlp.run_absa_pipeline import (
        get_pending_content_ids,
        get_pending_feedback_ids,
    )

    validation = {
        "unclean_contents": 0,
        "unclean_feedbacks": 0,
        "pending_absa_contents": 0,
        "pending_absa_feedbacks": 0,
        "missing_postgres_posts": 0,
        "missing_postgres_reviews": 0,
        "extra_postgres_posts": 0,
        "extra_postgres_reviews": 0,
    }
    client = _get_mongo_client()
    try:
        db = client[DB_NAME]
        post_ids: list[str] = []
        feedback_ids: list[str] = []
        if target in ("contents", "both"):
            validation["unclean_contents"] = len(
                get_unclean_ids(
                    CONTENTS_COLLECTION, CLEANED_CONTENTS_COLLECTION, db
                )
            )
            validation["pending_absa_contents"] = len(
                get_pending_content_ids(db, threshold)
            )
            post_ids = [str(value) for value in db[OUTPUT_CONTENTS].distinct("_id")]
        if target in ("feedbacks", "both"):
            validation["unclean_feedbacks"] = len(
                get_unclean_ids(
                    FEEDBACKS_COLLECTION, CLEANED_FEEDBACKS_COLLECTION, db
                )
            )
            validation["pending_absa_feedbacks"] = len(
                get_pending_feedback_ids(db, threshold)
            )
            feedback_ids = [
                str(value) for value in db[OUTPUT_FEEDBACKS].distinct("_id")
            ]
    finally:
        client.close()

    pool = await get_pool()
    async with pool.acquire() as conn:
        if target in ("contents", "both") and post_ids:
            validation["missing_postgres_posts"] = await conn.fetchval(
                "SELECT COUNT(*) FROM unnest($1::text[]) AS source(post_id) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM fact_social_posts target "
                "  WHERE target.post_id = source.post_id"
                ")",
                post_ids,
            )
            validation["extra_postgres_posts"] = await conn.fetchval(
                "SELECT COUNT(*) FROM fact_social_posts "
                "WHERE NOT (post_id = ANY($1::text[]))",
                post_ids,
            )
        elif target in ("contents", "both"):
            validation["extra_postgres_posts"] = await conn.fetchval(
                "SELECT COUNT(*) FROM fact_social_posts"
            )
        if target in ("feedbacks", "both") and feedback_ids:
            validation["missing_postgres_reviews"] = await conn.fetchval(
                "SELECT COUNT(*) FROM unnest($1::text[]) AS source(feedback_id) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM fact_review_absa_results target "
                "  WHERE target.feedback_id = source.feedback_id"
                ")",
                feedback_ids,
            )
            validation["extra_postgres_reviews"] = await conn.fetchval(
                "SELECT COUNT(DISTINCT feedback_id) "
                "FROM fact_review_absa_results "
                "WHERE NOT (feedback_id = ANY($1::text[]))",
                feedback_ids,
            )
        elif target in ("feedbacks", "both"):
            validation["extra_postgres_reviews"] = await conn.fetchval(
                "SELECT COUNT(DISTINCT feedback_id) "
                "FROM fact_review_absa_results"
            )
    return validation


def _format_etl_error(exc: BaseException) -> str:
    detail = str(exc).strip()
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


async def run_full_etl(
    reprocess: bool,
    threshold: float,
    user_id: str | None,
    target: str = "both",
) -> str:
    run_id = await _create_run("full", user_id)

    async def _execute() -> None:
        start = time.time()
        try:
            clean_stats = await asyncio.to_thread(
                _run_clean_sync, target, reprocess
            )
            absa_stats = await asyncio.to_thread(
                _run_absa_sync, target, reprocess, threshold
            )
            export_stats = await _export_to_postgres()
            validation = await _validate_pipeline_sync(target, threshold)
            remaining = sum(validation.values())
            if remaining:
                raise RuntimeError(
                    "Pipeline validation found "
                    f"{remaining} unpropagated records: {validation}"
                )
            elapsed = time.time() - start
            await _finish_run(run_id, "completed", stats={
                "target": target,
                "clean": clean_stats,
                "absa": absa_stats,
                "export": export_stats,
                "validation": validation,
                "duration": round(elapsed, 2),
            })
        except Exception as e:
            logger.exception("Full ETL run %s failed", run_id)
            await _finish_run(run_id, "failed", error=_format_etl_error(e))

    _start_tracked_task(_execute())
    return run_id


async def run_clean_etl(
    collection: str, reprocess: bool, user_id: str | None
) -> str:
    run_id = await _create_run("clean", user_id)

    async def _execute() -> None:
        try:
            stats = await asyncio.to_thread(_run_clean_sync, collection, reprocess)
            await _finish_run(run_id, "completed", stats=stats)
        except Exception as e:
            logger.exception("Cleaning ETL run %s failed", run_id)
            await _finish_run(run_id, "failed", error=_format_etl_error(e))

    _start_tracked_task(_execute())
    return run_id


async def run_absa_etl(
    pipeline: str, reprocess: bool, threshold: float, user_id: str | None
) -> str:
    run_id = await _create_run("absa", user_id)

    async def _execute() -> None:
        try:
            stats = await asyncio.to_thread(
                _run_absa_sync, pipeline, reprocess, threshold
            )
            await _finish_run(run_id, "completed", stats=stats)
        except Exception as e:
            logger.exception("ABSA ETL run %s failed", run_id)
            await _finish_run(run_id, "failed", error=_format_etl_error(e))

    _start_tracked_task(_execute())
    return run_id


async def run_export_etl(user_id: str | None) -> str:
    run_id = await _create_run("export", user_id)

    async def _execute() -> None:
        try:
            stats = await _export_to_postgres()
            await _finish_run(run_id, "completed", stats=stats)
        except Exception as e:
            logger.exception("Export ETL run %s failed", run_id)
            await _finish_run(run_id, "failed", error=_format_etl_error(e))

    _start_tracked_task(_execute())
    return run_id
