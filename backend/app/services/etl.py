from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from ..config import settings
from ..database import get_pool
from ..models.etl import (
    ETLRunHistory,
    ETLStatusResponse,
    MongoDBStatus,
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
    return [
        ETLRunHistory(
            run_id=r["run_id"],
            run_type=r["run_type"],
            status=r["status"],
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            duration_seconds=r["duration_seconds"],
            stats=json.loads(r["stats"]) if r["stats"] else None,
            error=r["error"],
        )
        for r in rows
    ]


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
        show_status,
        CONTENTS_COLLECTION as CC,
        FEEDBACKS_COLLECTION as FC,
        CLEANED_CONTENTS_COLLECTION as CLC,
        CLEANED_FEEDBACKS_COLLECTION as CLF,
    )

    db = get_db()
    total_stats: dict[str, Any] = {"processed": 0, "clean": 0, "filtered": 0, "empty": 0}

    if reprocess:
        if collection in ("contents", "both"):
            db[CLC].drop()
        if collection in ("feedbacks", "both"):
            db[CLF].drop()

    if collection in ("contents", "both"):
        unprocessed = get_unprocessed_ids(CC, CLC, db)
        if unprocessed:
            stats = process_contents(unprocessed, db)
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

    if collection in ("feedbacks", "both"):
        unprocessed = get_unprocessed_ids(FC, CLF, db)
        if unprocessed:
            stats = process_feedbacks(unprocessed, db)
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

    return total_stats


def _run_absa_sync(
    pipeline: str, reprocess: bool, threshold: float
) -> dict[str, Any]:
    global _aspect_tokenizer, _aspect_model
    global _sentiment_tokenizer, _sentiment_model
    global _device, _dtype, _batch_size

    from nlp.run_absa_pipeline import (
        get_db,
        detect_device,
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

    if _aspect_model is None:
        _device, _dtype, _batch_size = detect_device()
        models_dir = DEFAULT_MODELS_DIR if DEFAULT_MODELS_DIR.exists() else None

        aspect_source = _resolve_model_path(models_dir, ASPECT_MODEL_FOLDER, ASPECT_MODEL_ID)
        _aspect_tokenizer = AutoTokenizer.from_pretrained(aspect_source)
        _aspect_model = AutoModelForSequenceClassification.from_pretrained(
            aspect_source, torch_dtype=_dtype
        ).to(_device)
        _aspect_model.eval()

    if _sentiment_model is None and pipeline in ("feedbacks", "both"):
        models_dir = DEFAULT_MODELS_DIR if DEFAULT_MODELS_DIR.exists() else None
        sentiment_source = _resolve_model_path(models_dir, SENTIMENT_MODEL_FOLDER, SENTIMENT_MODEL_ID)
        _sentiment_tokenizer = AutoTokenizer.from_pretrained(sentiment_source)
        _sentiment_model = AutoModelForSequenceClassification.from_pretrained(
            sentiment_source, torch_dtype=_dtype
        ).to(_device)
        _sentiment_model.eval()

    client, db = get_db()
    try:
        if reprocess:
            if pipeline in ("feedbacks", "both"):
                db[OUTPUT_FEEDBACKS].drop()
            if pipeline in ("contents", "both"):
                db[OUTPUT_CONTENTS].drop()

        stats: dict[str, Any] = {}

        if pipeline in ("feedbacks", "both"):
            fb_stats = run_feedbacks_pipeline(
                db,
                _aspect_tokenizer, _aspect_model,
                _sentiment_tokenizer, _sentiment_model,
                _device, _dtype, _batch_size, threshold,
            )
            stats["feedbacks"] = fb_stats

        if pipeline in ("contents", "both"):
            ct_stats = run_contents_pipeline(
                db,
                _aspect_tokenizer, _aspect_model,
                _device, _dtype, _batch_size, threshold,
            )
            stats["contents"] = ct_stats

    finally:
        client.close()

    return stats


async def _export_to_postgres() -> dict[str, int]:
    client = _get_mongo_client()
    try:
        db = client[DB_NAME]

        def _read_mongo() -> tuple[list[dict], list[dict], set[tuple[str, str]]]:
            entities: set[tuple[str, str]] = set()
            for col in [OUTPUT_FEEDBACKS, OUTPUT_CONTENTS]:
                for doc in db[col].find({}, {"entity_name": 1, "platform": 1}):
                    name = doc.get("entity_name", "")
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
    result: dict[str, int] = {"entities": 0, "posts": 0, "reviews": 0}

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
                key = (name, platform)
                if key not in entity_cache:
                    entity_cache[key] = await conn.fetchval(
                        "SELECT entity_id FROM dim_entities "
                        "WHERE entity_name = $1 AND platform = $2",
                        name, platform,
                    )
                return entity_cache[key]

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
                    "  sad_count, angry_count, care_count,"
                    "  shares_count, comments_count,"
                    "  positivity_ratio, negativity_ratio"
                    ") VALUES ("
                    "  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17"
                    ") ON CONFLICT (post_id) DO UPDATE SET "
                    "  entity_id=EXCLUDED.entity_id, post_timestamp=EXCLUDED.post_timestamp,"
                    "  post_text=EXCLUDED.post_text, promoted_aspects=EXCLUDED.promoted_aspects,"
                    "  aspect_confidence=EXCLUDED.aspect_confidence,"
                    "  total_reactions=EXCLUDED.total_reactions,"
                    "  like_count=EXCLUDED.like_count, love_count=EXCLUDED.love_count,"
                    "  haha_count=EXCLUDED.haha_count, sad_count=EXCLUDED.sad_count,"
                    "  angry_count=EXCLUDED.angry_count, care_count=EXCLUDED.care_count,"
                    "  shares_count=EXCLUDED.shares_count, comments_count=EXCLUDED.comments_count,"
                    "  positivity_ratio=EXCLUDED.positivity_ratio,"
                    "  negativity_ratio=EXCLUDED.negativity_ratio",
                    doc["_id"], eid, doc.get("post_timestamp"),
                    doc.get("post_text"), doc.get("promoted_aspects"),
                    aspect_conf,
                    doc.get("total_reactions"), doc.get("like_count"),
                    doc.get("love_count"), doc.get("haha_count"),
                    doc.get("sad_count"), doc.get("angry_count"),
                    doc.get("care_count"), doc.get("shares_count"),
                    doc.get("comments_count"), doc.get("positivity_ratio"),
                    doc.get("negativity_ratio"),
                )
                result["posts"] += 1

            if feedbacks:
                feedback_ids = [
                    doc.get("feedback_id", doc["_id"]) for doc in feedbacks
                ]
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


async def run_full_etl(
    reprocess: bool, threshold: float, user_id: str | None
) -> str:
    run_id = await _create_run("full", user_id)

    async def _execute() -> None:
        start = time.time()
        try:
            clean_stats = await asyncio.to_thread(
                _run_clean_sync, "both", reprocess
            )
            absa_stats = await asyncio.to_thread(
                _run_absa_sync, "both", reprocess, threshold
            )
            export_stats = await _export_to_postgres()
            elapsed = time.time() - start
            await _finish_run(run_id, "completed", stats={
                "clean": clean_stats,
                "absa": absa_stats,
                "export": export_stats,
                "duration": round(elapsed, 2),
            })
        except Exception as e:
            await _finish_run(run_id, "failed", error=str(e))

    asyncio.create_task(_execute())
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
            await _finish_run(run_id, "failed", error=str(e))

    asyncio.create_task(_execute())
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
            await _finish_run(run_id, "failed", error=str(e))

    asyncio.create_task(_execute())
    return run_id


async def run_export_etl(user_id: str | None) -> str:
    run_id = await _create_run("export", user_id)

    async def _execute() -> None:
        try:
            stats = await _export_to_postgres()
            await _finish_run(run_id, "completed", stats=stats)
        except Exception as e:
            await _finish_run(run_id, "failed", error=str(e))

    asyncio.create_task(_execute())
    return run_id
