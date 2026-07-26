"""
30-Day lifecycle tracking (MongoDB-backed) and MongoDB connection helpers.

This module is the I/O boundary between the in-memory scraper data and
MongoDB. It contains:
  - `save_content_obj_to_mongo` / `save_session_data_to_mongo`
  - `get_db` / `ensure_mongo_indexes`
  - `show_tracking_status_db`

Shared utility helpers (parse_scraped_datetime, normalize_ui_text,
normalize_source_url, make_scoped_id) live in `_common` and are re-imported
here for convenience.
"""

from __future__ import annotations

from datetime import datetime

from pymongo import MongoClient, UpdateOne

from ._common import make_scoped_id, normalize_source_url, parse_scraped_datetime
from ._config import (
    CONTENTS_COLLECTION,
    DB_NAME,
    FEEDBACKS_COLLECTION,
    LIFECYCLE_DAYS,
    MONGO_URI,
)
from .storage import session_data

__all__ = [
    "save_content_obj_to_mongo",
    "save_session_data_to_mongo",
    "get_db",
    "ensure_mongo_indexes",
    "show_tracking_status_db",
    "make_scoped_id",
    "normalize_source_url",
    "parse_scraped_datetime",
]


def save_content_obj_to_mongo(db, content_obj):
    """Persist one in-memory source content object and its feedbacks to MongoDB."""
    now = datetime.now()
    content_id = content_obj.get('source_content_id')
    if not content_id:
        print("[MONGO][WARN] Skipped content without source_content_id.")
        return {'contents_upserted': 0, 'contents_modified': 0, 'feedbacks_upserted': 0, 'feedbacks_modified': 0}

    feedbacks = content_obj.get('feedbacks', [])
    content_doc = {
        "source_type": content_obj.get("source_type", ""),
        "entity_name": content_obj.get("entity_name", ""),
        "source_content_id": content_id,
        "title_or_post": content_obj.get("title_or_post", ""),
        "overall_rating": content_obj.get("overall_rating"),
        "review_diagnostics": content_obj.get("review_diagnostics", {}),
        "last_updated_at": now,
        "comment_count": len(feedbacks),
        "feedback_count": len(feedbacks),
    }
    diagnostics = content_obj.get("review_diagnostics", {})
    if diagnostics.get("canonical_shop_url"):
        content_doc["page_url"] = diagnostics["canonical_shop_url"]
    elif diagnostics.get("final_url"):
        content_doc["page_url"] = diagnostics["final_url"]

    content_result = db[CONTENTS_COLLECTION].update_one(
        {"_id": content_id},
        {
            "$set": content_doc,
            "$setOnInsert": {"first_scraped_at": now},
        },
        upsert=True,
    )

    feedback_ops = []
    for fb in feedbacks:
        feedback_id = fb.get("id") or fb.get("source_feedback_id")
        if not feedback_id:
            feedback_id = make_scoped_id("feedback", content_id, fb.get("author", ""), fb.get("raw_text", ""))
        feedback_date = parse_scraped_datetime(
            fb.get("timestamp") or fb.get("feedback_date"), fallback=now)
        raw_text = fb.get("raw_text") or fb.get("text") or ""
        feedback_ops.append(UpdateOne(
            {"_id": feedback_id},
            {"$set": {
                "content_id": content_id,
                "entity_name": content_obj.get("entity_name", ""),
                "source_type": content_obj.get("source_type", ""),
                "source_feedback_id": fb.get("source_feedback_id", feedback_id),
                "platform_review_id": fb.get("platform_review_id", ""),
                "source": fb.get("source", ""),
                "author": fb.get("author", "Unknown"),
                "raw_text": raw_text,
                "rating": fb.get("rating"),
                "raw_timestamp": fb.get("raw_timestamp", ""),
                "feedback_date": feedback_date,
                "scraped_at": now,
            }},
            upsert=True,
        ))

    feedback_result = None
    if feedback_ops:
        feedback_result = db[FEEDBACKS_COLLECTION].bulk_write(feedback_ops, ordered=False)

    return {
        'contents_upserted': 1 if content_result.upserted_id else 0,
        'contents_modified': content_result.modified_count,
        'feedbacks_upserted': feedback_result.upserted_count if feedback_result else 0,
        'feedbacks_modified': feedback_result.modified_count if feedback_result else 0,
    }


def save_session_data_to_mongo(db):
    totals = {'contents_upserted': 0, 'contents_modified': 0, 'feedbacks_upserted': 0, 'feedbacks_modified': 0}
    for content_obj in session_data:
        result = save_content_obj_to_mongo(db, content_obj)
        for key in totals:
            totals[key] += result.get(key, 0)
    print(
        f"[MONGO] Session data saved: contents {totals['contents_upserted']} inserted, "
        f"{totals['contents_modified']} updated | feedbacks {totals['feedbacks_upserted']} inserted, "
        f"{totals['feedbacks_modified']} updated."
    )
    return totals


def get_db():
    """
    MongoDB သို့ ချိတ်ဆက်ပြီး (client, db) tuple ပြန်ပေးသည်။
    Connection မရပါက ရှင်းလင်းသော error ပြပြီး raise လုပ်သည်။
    """
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
    except Exception as e:
        print(f"\n[ERROR] MongoDB not reachable at {MONGO_URI}: {e}")
        print("[HINT] Start MongoDB first: docker-compose up -d")
        raise
    db = client[DB_NAME]
    ensure_mongo_indexes(db)
    return client, db


def ensure_mongo_indexes(db):
    """Create the indexes used by lifecycle, source scoping, and feedback lookup."""
    try:
        db[CONTENTS_COLLECTION].create_index(
            [("page_url", 1), ("lifecycle_status", 1), ("expires_at", 1)]
        )
        db[CONTENTS_COLLECTION].create_index([("source_type", 1), ("entity_name", 1)])
        db[CONTENTS_COLLECTION].create_index(
            [("source_type", 1), ("content_hash", 1)],
            sparse=True,
        )
        db[FEEDBACKS_COLLECTION].create_index([("content_id", 1), ("feedback_date", -1)])
    except Exception as exc:
        print(f"[WARN] Mongo index creation skipped: {type(exc).__name__}: {exc}")


def show_tracking_status_db(db):
    """Print lifecycle and reaction-breakdown status from MongoDB."""
    contents_col = db[CONTENTS_COLLECTION]
    tracking_count = contents_col.count_documents({"lifecycle_status": "tracking"})
    final_count = contents_col.count_documents({"lifecycle_status": "final"})
    total_count = contents_col.count_documents({})
    now = datetime.now()

    print(f"\n{'='*60}")
    print(f"{LIFECYCLE_DAYS}-Day Post Tracking Status (MongoDB)")
    print(f"{'='*60}")
    print(f"   Actively Tracking: {tracking_count} posts")
    print(f"   Finalized:         {final_count} posts")
    print(f"   Total Tracked:     {total_count} posts")

    if total_count == 0:
        print("\n[INFO] No content is being tracked yet.")
        return

    recent = contents_col.find().sort("last_updated_at", -1).limit(10)
    print("\n   RECENTLY UPDATED CONTENT")
    for doc in recent:
        preview = str(doc.get("title_or_post") or doc.get("_id"))[:45]
        status = doc.get("lifecycle_status", "?")
        scrapes = doc.get("scrape_count", 1)
        expires_at = doc.get("expires_at")
        if status == "tracking" and isinstance(expires_at, datetime):
            extra = f"Days left: {max(0, (expires_at - now).days)}"
        else:
            extra = "archived" if status == "final" else "n/a"
        history = doc.get("engagement_history", [])
        latest = history[-1] if history else doc
        total = (latest.get("reactions_breakdown") or {}).get("total")
        reaction_status = (doc.get("reaction_diagnostics") or {}).get("status", "unknown")
        print(f"   - [{status}] {preview}...")
        print(f"     Scrapes: {scrapes} | {extra} | {total} reactions ({reaction_status})")

    print(f"\n{'='*60}")
