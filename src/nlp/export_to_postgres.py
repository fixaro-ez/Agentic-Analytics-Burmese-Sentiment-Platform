"""
ABSA → PostgreSQL Export Script
───────────────────────────────
Reads from MongoDB ABSA collections and writes to PostgreSQL star schema.

Tables:
  dim_entities            ← DISTINCT entity_name + platform from both collections
  fact_social_posts       ← absa_processed_contents (1:1)
  fact_review_absa_results ← absa_processed_feedbacks (long format, 1:N)

Usage:
  PYTHONPATH=src python -m nlp.export_to_postgres
  PYTHONPATH=src python -m nlp.export_to_postgres --dry-run
  PYTHONPATH=src python -m nlp.export_to_postgres --status
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2
import psycopg2.extras
from pymongo import MongoClient

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

try:
    from dotenv import load_dotenv
except ImportError:
    print("[ERROR] python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

load_dotenv()


MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "feedback_analytics"
OUTPUT_FEEDBACKS = "absa_processed_feedbacks"
OUTPUT_CONTENTS = "absa_processed_contents"


def get_mongo_db():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
    except Exception as e:
        print(f"\n[ERROR] MongoDB not reachable at {MONGO_URI}: {e}")
        print("[HINT] Start MongoDB first: docker-compose up -d")
        raise
    return client, client[DB_NAME]


def get_pg_connection():
    host = os.environ.get("PG_HOST")
    port = int(os.environ.get("PG_PORT", "5432"))
    user = os.environ.get("PG_USER")
    password = os.environ.get("PG_PASSWORD")
    dbname = os.environ.get("PG_DBNAME", "postgres")

    if not all([host, user, password]):
        print("[ERROR] Missing PG_HOST, PG_USER, or PG_PASSWORD in .env file")
        sys.exit(1)

    try:
        conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
        conn.autocommit = False
    except Exception as e:
        print(f"\n[ERROR] PostgreSQL connection failed: {e}")
        print("[HINT] Check PG_* fields in .env file")
        raise
    return conn


def export_dim_entities(db, cur, dry_run: bool = False) -> int:
    entities: set[tuple[str, str]] = set()

    for col_name in [OUTPUT_FEEDBACKS, OUTPUT_CONTENTS]:
        for doc in db[col_name].find({}, {"entity_name": 1, "platform": 1}):
            name = doc.get("entity_name", "")
            platform = doc.get("platform", "")
            if name and platform:
                entities.add((name, platform))

    if not entities:
        print("[dim_entities] No entities found.")
        return 0

    print(f"[dim_entities] Found {len(entities)} unique entities")

    if dry_run:
        for name, platform in entities:
            print(f"  Would insert: {name} ({platform})")
        return len(entities)

    insert_sql = """
        INSERT INTO dim_entities (entity_name, platform)
        VALUES (%s, %s)
        ON CONFLICT (entity_name, platform) DO NOTHING
        RETURNING entity_id
    """
    for name, platform in entities:
        cur.execute(insert_sql, (name, platform))
        result = cur.fetchone()
        if result:
            print(f"  Inserted: {name} ({platform}) → entity_id={result[0]}")
        else:
            print(f"  Skipped (exists): {name} ({platform})")

    return len(entities)


def build_entity_map(db) -> dict[tuple[str, str], int]:
    entity_map: dict[tuple[str, str], int] = {}
    return entity_map


def get_entity_id(cur, entity_name: str, platform: str) -> int | None:
    cur.execute(
        "SELECT entity_id FROM dim_entities WHERE entity_name = %s AND platform = %s",
        (entity_name, platform),
    )
    row = cur.fetchone()
    return row[0] if row else None


def export_fact_social_posts(db, cur, dry_run: bool = False) -> int:
    docs = list(db[OUTPUT_CONTENTS].find({}))

    if not docs:
        print("[fact_social_posts] No documents found.")
        return 0

    print(f"[fact_social_posts] Found {len(docs)} documents")

    if dry_run:
        for doc in docs:
            print(f"  Would insert: {doc['_id']} ({doc.get('entity_name')}, {doc.get('platform')})")
        return len(docs)

    upsert_sql = """
        INSERT INTO fact_social_posts (
            post_id, entity_id, post_timestamp, post_text,
            promoted_aspects, aspect_confidence,
            total_reactions, like_count, love_count, haha_count,
            sad_count, angry_count, care_count, wow_count,
            shares_count, comments_count,
            positivity_ratio, negativity_ratio
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (post_id) DO UPDATE SET
            entity_id = EXCLUDED.entity_id,
            post_timestamp = EXCLUDED.post_timestamp,
            post_text = EXCLUDED.post_text,
            promoted_aspects = EXCLUDED.promoted_aspects,
            aspect_confidence = EXCLUDED.aspect_confidence,
            total_reactions = EXCLUDED.total_reactions,
            like_count = EXCLUDED.like_count,
            love_count = EXCLUDED.love_count,
            haha_count = EXCLUDED.haha_count,
            sad_count = EXCLUDED.sad_count,
            angry_count = EXCLUDED.angry_count,
            care_count = EXCLUDED.care_count,
            wow_count = EXCLUDED.wow_count,
            shares_count = EXCLUDED.shares_count,
            comments_count = EXCLUDED.comments_count,
            positivity_ratio = EXCLUDED.positivity_ratio,
            negativity_ratio = EXCLUDED.negativity_ratio
    """

    count = 0
    for doc in docs:
        entity_id = get_entity_id(cur, doc.get("entity_name", ""), doc.get("platform", ""))
        if entity_id is None:
            print(f"  [WARN] No entity_id for: {doc.get('entity_name')} ({doc.get('platform')})")
            continue

        aspect_confidence_json = json.dumps(doc.get("aspect_probabilities")) if doc.get("aspect_probabilities") else None

        cur.execute(upsert_sql, (
            doc["_id"],
            entity_id,
            doc.get("post_timestamp"),
            doc.get("post_text"),
            doc.get("promoted_aspects"),
            aspect_confidence_json,
            doc.get("total_reactions"),
            doc.get("like_count"),
            doc.get("love_count"),
            doc.get("haha_count"),
            doc.get("sad_count"),
            doc.get("angry_count"),
            doc.get("care_count"),
            doc.get("wow_count"),
            doc.get("shares_count"),
            doc.get("comments_count"),
            doc.get("positivity_ratio"),
            doc.get("negativity_ratio"),
        ))
        count += 1

    print(f"  Inserted/upserted {count} posts")
    return count


def export_fact_reviews(db, cur, dry_run: bool = False) -> int:
    docs = list(db[OUTPUT_FEEDBACKS].find({}))

    if not docs:
        print("[fact_review_absa_results] No documents found.")
        return 0

    print(f"[fact_review_absa_results] Found {len(docs)} feedback documents")

    rows: list[tuple] = []
    for doc in docs:
        feedback_id = doc.get("feedback_id", doc["_id"])
        feedback_ts = doc.get("feedback_timestamp")
        raw_text = doc.get("raw_text")
        aspect_sentiments = doc.get("aspect_sentiments", [])

        if dry_run:
            entity_id = None
        else:
            entity_id = get_entity_id(cur, doc.get("entity_name", ""), doc.get("platform", ""))
            if entity_id is None:
                print(f"  [WARN] No entity_id for: {doc.get('entity_name')} ({doc.get('platform')})")
                continue

        if not aspect_sentiments:
            rows.append((feedback_id, entity_id, feedback_ts, raw_text, "no_aspect", None, None))
        else:
            for item in aspect_sentiments:
                rows.append((
                    feedback_id,
                    entity_id,
                    feedback_ts,
                    raw_text,
                    item.get("aspect"),
                    item.get("sentiment"),
                    item.get("confidence"),
                ))

    print(f"  Expanded to {len(rows)} long-format rows")

    if dry_run:
        for row in rows[:5]:
            print(f"  Would insert: feedback={row[0]}, aspect={row[4]}, sentiment={row[5]}")
        if len(rows) > 5:
            print(f"  ... and {len(rows) - 5} more")
        return len(rows)

    delete_ids = [doc.get("feedback_id", doc["_id"]) for doc in docs]
    if delete_ids:
        cur.execute(
            "DELETE FROM fact_review_absa_results WHERE feedback_id = ANY(%s)",
            (delete_ids,),
        )

    insert_sql = """
        INSERT INTO fact_review_absa_results (
            feedback_id, entity_id, feedback_timestamp,
            raw_text, aspect_category, sentiment_label, confidence_score
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=500)

    print(f"  Inserted {len(rows)} rows")
    return len(rows)


def show_status(conn) -> None:
    cur = conn.cursor()
    print(f"\n{'=' * 60}")
    print("POSTGRESQL STATUS")
    print(f"{'=' * 60}")

    tables = [
        ("dim_entities", "entity_id"),
        ("fact_social_posts", "post_id"),
        ("fact_review_absa_results", "result_id"),
    ]

    for table, pk in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            print(f"  {table}: ERROR - {e}")
            conn.rollback()

    print(f"\n{'=' * 60}")
    cur.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export ABSA data from MongoDB to PostgreSQL (Supabase)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to PostgreSQL",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show PostgreSQL table row counts and exit",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.status:
        conn = get_pg_connection()
        try:
            show_status(conn)
        finally:
            conn.close()
        return

    print(f"\n{'=' * 60}")
    print("ABSA → POSTGRESQL EXPORT")
    print(f"{'=' * 60}")
    print(f"  Dry-run: {args.dry_run}")
    print(f"{'=' * 60}\n")

    mongo_client, db = get_mongo_db()

    if args.dry_run:
        conn = None
        cur = None
    else:
        conn = get_pg_connection()
        cur = conn.cursor()

    try:
        print("Step 1: Export dim_entities...")
        export_dim_entities(db, cur, dry_run=args.dry_run)

        print("\nStep 2: Export fact_social_posts...")
        export_fact_social_posts(db, cur, dry_run=args.dry_run)

        print("\nStep 3: Export fact_review_absa_results...")
        export_fact_reviews(db, cur, dry_run=args.dry_run)

        if args.dry_run:
            print("\n[DRY RUN] No data was written to PostgreSQL.")
        else:
            conn.commit()
            print("\n[OK] All data committed to PostgreSQL.")
            show_status(conn)
            cur.close()

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\n[ERROR] Transaction rolled back: {e}")
        raise

    finally:
        if conn:
            conn.close()
        mongo_client.close()


if __name__ == "__main__":
    main()
