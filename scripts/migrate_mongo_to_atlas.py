"""Copy the local feedback_analytics MongoDB database to MongoDB Atlas.

This is an idempotent logical migration. It preserves document _ids and
recreates non-_id indexes after copying documents. The target database is
expected to be empty unless --allow-existing is supplied.

Usage (from the repository root):
    python scripts/migrate_mongo_to_atlas.py --dry-run
    python scripts/migrate_mongo_to_atlas.py

The Atlas URI is read from backend/.env as MONGO_URI and is never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from pymongo import MongoClient, ReplaceOne


DB_NAME = "feedback_analytics"
COLLECTIONS = (
    "contents",
    "feedbacks",
    "cleaned_contents",
    "cleaned_feedbacks",
    "absa_processed_contents",
    "absa_processed_feedbacks",
)
SOURCE_URI = "mongodb://localhost:27017"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path("backend/.env"),
        help="File containing MONGO_URI (default: backend/.env)",
    )
    parser.add_argument(
        "--source-uri",
        default=SOURCE_URI,
        help="Source MongoDB URI (default: local Docker MongoDB)",
    )
    parser.add_argument(
        "--db",
        default=DB_NAME,
        help=f"Database to copy (default: {DB_NAME})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify connections and show counts without writing to Atlas",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow upserting into a non-empty target database",
    )
    return parser.parse_args()


def load_target_uri(env_file: Path) -> str:
    uri = os.environ.get("MONGO_URI")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("MONGO_URI="):
                uri = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not uri:
        raise RuntimeError(f"MONGO_URI was not found in {env_file}")
    return uri


def ping(client: MongoClient, label: str) -> None:
    client.admin.command("ping")
    print(f"[ok] {label} connection")


def collection_counts(db: Any) -> dict[str, int]:
    return {name: db[name].count_documents({}) for name in COLLECTIONS}


def copy_indexes(source_collection: Any, target_collection: Any) -> int:
    """Recreate source indexes, excluding MongoDB's automatic _id index."""
    created = 0
    for index in source_collection.list_indexes():
        if index["name"] == "_id_":
            continue

        # These are the portable index options used by this project. MongoDB
        # adds metadata fields (key, ns, v) that must not be passed to create.
        options = {
            key: index[key]
            for key in (
                "name",
                "unique",
                "sparse",
                "expireAfterSeconds",
                "partialFilterExpression",
                "collation",
                "hidden",
                "weights",
                "default_language",
                "language_override",
                "wildcardProjection",
            )
            if key in index
        }
        target_collection.create_index(list(index["key"].items()), **options)
        created += 1
    return created


def copy_collection(source_collection: Any, target_collection: Any) -> tuple[int, int]:
    operations: list[ReplaceOne] = []
    copied = 0
    for document in source_collection.find({}):
        operations.append(ReplaceOne({"_id": document["_id"]}, document, upsert=True))
        if len(operations) >= 250:
            target_collection.bulk_write(operations, ordered=False)
            copied += len(operations)
            operations.clear()

    if operations:
        target_collection.bulk_write(operations, ordered=False)
        copied += len(operations)

    indexes = copy_indexes(source_collection, target_collection)
    return copied, indexes


def validate_document_ids(source_db: Any, target_db: Any) -> None:
    for name in COLLECTIONS:
        source_ids = {document["_id"] for document in source_db[name].find({}, {"_id": 1})}
        target_ids = {document["_id"] for document in target_db[name].find({}, {"_id": 1})}
        if source_ids != target_ids:
            raise RuntimeError(f"Validation failed: document IDs differ for {name}")
    print("[ok] Atlas document IDs match the local source")


def main() -> int:
    args = parse_args()
    try:
        target_uri = load_target_uri(args.env_file)
        source_client = MongoClient(args.source_uri, serverSelectionTimeoutMS=10_000)
        target_client = MongoClient(target_uri, serverSelectionTimeoutMS=20_000)
        ping(source_client, "local MongoDB")
        ping(target_client, "MongoDB Atlas")

        source_db = source_client[args.db]
        target_db = target_client[args.db]
        source_counts = collection_counts(source_db)
        target_counts = collection_counts(target_db)

        print("Source counts:")
        for name, count in source_counts.items():
            print(f"  {name}: {count}")
        print("Target counts before migration:")
        for name, count in target_counts.items():
            print(f"  {name}: {count}")

        if args.dry_run:
            validate_document_ids(source_db, target_db)
            print("[dry-run] No documents or indexes were written.")
            return 0

        if not args.allow_existing and any(target_counts.values()):
            raise RuntimeError(
                "Atlas already contains documents in feedback_analytics. "
                "Stop and inspect the target, or rerun with --allow-existing."
            )

        print("Copying documents and indexes...")
        for name in COLLECTIONS:
            copied, indexes = copy_collection(source_db[name], target_db[name])
            print(f"  {name}: {copied} documents, {indexes} indexes")

        final_counts = collection_counts(target_db)
        if final_counts != source_counts:
            print("Final target counts:", final_counts, file=sys.stderr)
            raise RuntimeError("Validation failed: Atlas counts do not match the source")

        print("[ok] Atlas counts match the local source")
        validate_document_ids(source_db, target_db)
        return 0
    except Exception as exc:
        print(f"[error] Migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        for client_name in ("source_client", "target_client"):
            client = locals().get(client_name)
            if client is not None:
                client.close()


if __name__ == "__main__":
    raise SystemExit(main())
