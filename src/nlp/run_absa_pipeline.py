"""
Burmese ABSA Inference Pipeline
────────────────────────────────
Two-stage aspect-based sentiment analysis on cleaned Burmese text from MongoDB.

Pipeline 1 (Foodpanda Reviews):  Stage 1 (Aspects) + Stage 2 (Sentiment)
Pipeline 2 (Facebook Posts):     Stage 1 (Aspects) only

Usage:
  PYTHONPATH=src python -m nlp.run_absa_pipeline
  PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline feedbacks
  PYTHONPATH=src python -m nlp.run_absa_pipeline --pipeline contents
  PYTHONPATH=src python -m nlp.run_absa_pipeline --device cuda --batch-size 64
  PYTHONPATH=src python -m nlp.run_absa_pipeline --reprocess
  PYTHONPATH=src python -m nlp.run_absa_pipeline --dry-run
  PYTHONPATH=src python -m nlp.run_absa_pipeline --status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

import torch
from pymongo import MongoClient, ReplaceOne
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from burmese_absa.mongo_config import MONGO_URI

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass


DB_NAME = "feedback_analytics"

CLEANED_FEEDBACKS = "cleaned_feedbacks"
CLEANED_CONTENTS = "cleaned_contents"
OUTPUT_FEEDBACKS = "absa_processed_feedbacks"
OUTPUT_CONTENTS = "absa_processed_contents"

BATCH_FETCH_SIZE = 500

ASPECT_LABELS = [
    "product_or_service_quality",
    "fulfillment_and_speed",
    "price_and_value",
    "digital_experience",
    "customer_support",
    "variety_and_availability",
]

SENTIMENT_LABELS = ["Negative", "Neutral", "Positive"]

ASPECT_MODEL_ID = "Fixaro/myanmar-absa-aspect-detection"
SENTIMENT_MODEL_ID = "Fixaro/myanmar-absa-sentiment-classification"

ASPECT_MODEL_FOLDER = "stage1_xlm_roberta_large"
SENTIMENT_MODEL_FOLDER = "stage2_xlm_roberta_base"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_DIR = REPO_ROOT / "models"

DEFAULT_THRESHOLD = 0.5
GPU_BATCH_SIZE = 32
CPU_BATCH_SIZE = 8
ABSA_PIPELINE_VERSION = "2026-08-01-v1"


def detect_device() -> tuple[str, torch.dtype, int]:
    if torch.cuda.is_available():
        return "cuda", torch.bfloat16, GPU_BATCH_SIZE
    return "cpu", torch.float32, CPU_BATCH_SIZE


def get_db(mongo_uri: str | None = None) -> tuple[MongoClient, Any]:
    try:
        resolved_uri = mongo_uri or MONGO_URI
        client = MongoClient(resolved_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
    except Exception as e:
        print(f"\n[ERROR] MongoDB not reachable at {mongo_uri or MONGO_URI}: {e}")
        print("[HINT] Start MongoDB first: docker-compose up -d")
        raise
    db = client[DB_NAME]
    ensure_absa_indexes(db)
    return client, db


def ensure_absa_indexes(db: Any) -> None:
    try:
        db[OUTPUT_FEEDBACKS].create_index([("entity_name", 1), ("feedback_timestamp", -1)])
        db[OUTPUT_CONTENTS].create_index([("entity_name", 1), ("post_timestamp", -1)])
    except Exception as exc:
        print(f"[WARN] Index creation skipped: {type(exc).__name__}: {exc}")


def _processing_fingerprint(
    doc: dict[str, Any],
    *,
    pipeline: str,
    threshold: float,
) -> str:
    """Version ABSA outputs by source state, models, and threshold."""
    source_fingerprint = doc.get("source_fingerprint")
    if not source_fingerprint:
        fallback_fields = (
            (
                "content_id",
                "entity_name",
                "cleaned_text",
                "feedback_timestamp",
                "platform",
                "rating",
            )
            if pipeline == "feedbacks"
            else (
                "entity_name",
                "cleaned_text",
                "post_timestamp",
                "platform",
                "positivity_ratio",
                "negativity_ratio",
                "total_reactions",
                "like_count",
                "love_count",
                "haha_count",
                "sad_count",
                "angry_count",
                "care_count",
                "wow_count",
                "shares_count",
                "comments_count",
            )
        )
        source_fingerprint = hashlib.sha256(
            json.dumps(
                {field: doc.get(field) for field in fallback_fields},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=lambda item: item.isoformat()
                if isinstance(item, datetime)
                else str(item),
            ).encode("utf-8")
        ).hexdigest()
    payload = {
        "source_fingerprint": source_fingerprint,
        "pipeline": pipeline,
        "pipeline_version": ABSA_PIPELINE_VERSION,
        "aspect_model": ASPECT_MODEL_ID,
        "sentiment_model": (
            SENTIMENT_MODEL_ID if pipeline == "feedbacks" else None
        ),
        "threshold": round(float(threshold), 6),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def get_unprocessed_ids(
    source_col: str,
    output_col: str,
    db: Any,
    *,
    source_filter: dict[str, Any] | None = None,
    pipeline: str | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> set[str]:
    """
    Return eligible IDs whose ABSA representation is missing or stale.

    The old implementation compared IDs only, so updated text, reactions, and
    model thresholds never propagated after the first successful run.
    """
    if pipeline is None:
        source_ids = {
            doc["_id"]
            for doc in db[source_col].find(source_filter or {}, {"_id": 1})
        }
        output_ids = {
            doc["_id"] for doc in db[output_col].find({}, {"_id": 1})
        }
        return source_ids - output_ids

    output_fingerprints = {
        doc["_id"]: doc.get("processing_fingerprint")
        for doc in db[output_col].find(
            {}, {"_id": 1, "processing_fingerprint": 1}
        )
    }
    return {
        doc["_id"]
        for doc in db[source_col].find(source_filter or {})
        if output_fingerprints.get(doc["_id"])
        != _processing_fingerprint(
            doc, pipeline=pipeline, threshold=threshold
        )
    }


def get_pending_feedback_ids(db: Any, threshold: float) -> set[str]:
    return get_unprocessed_ids(
        CLEANED_FEEDBACKS,
        OUTPUT_FEEDBACKS,
        db,
        source_filter={
            "cleaning_status": "clean",
            "cleaned_text": {"$exists": True, "$ne": ""},
        },
        pipeline="feedbacks",
        threshold=threshold,
    )


def get_pending_content_ids(db: Any, threshold: float) -> set[str]:
    return get_unprocessed_ids(
        CLEANED_CONTENTS,
        OUTPUT_CONTENTS,
        db,
        source_filter={
            "platform": "facebook",
            "cleaning_status": "clean",
            "cleaned_text": {"$exists": True, "$ne": ""},
        },
        pipeline="contents",
        threshold=threshold,
    )


def remove_ineligible_outputs(db: Any, pipeline: str) -> int:
    """Remove derived ABSA documents whose cleaned source is no longer eligible."""
    if pipeline == "contents":
        source_col = CLEANED_CONTENTS
        output_col = OUTPUT_CONTENTS
        source_filter = {
            "platform": "facebook",
            "cleaning_status": "clean",
            "cleaned_text": {"$exists": True, "$ne": ""},
        }
    elif pipeline == "feedbacks":
        source_col = CLEANED_FEEDBACKS
        output_col = OUTPUT_FEEDBACKS
        source_filter = {
            "cleaning_status": "clean",
            "cleaned_text": {"$exists": True, "$ne": ""},
        }
    else:
        raise ValueError(f"Unknown ABSA pipeline: {pipeline}")

    eligible_ids = db[source_col].distinct("_id", source_filter)
    result = db[output_col].delete_many({"_id": {"$nin": eligible_ids}})
    return int(result.deleted_count or 0)


def _resolve_model_path(
    models_dir: Path | None,
    folder: str,
    hub_id: str,
) -> str:
    if models_dir is not None:
        local = models_dir / folder
        if local.exists() and (local / "config.json").exists():
            print(f"  Loading from local: {local}")
            return str(local)
    print(f"  Downloading from HuggingFace: {hub_id}")
    return hub_id


def predict_aspects(
    texts: list[str],
    tokenizer: AutoTokenizer,
    model: AutoModelForSequenceClassification,
    device: str,
    dtype: torch.dtype,
    threshold: float,
    batch_size: int,
) -> tuple[list[list[str]], list[dict[str, float]]]:
    all_predictions: list[list[str]] = []
    all_probabilities: list[dict[str, float]] = []

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        inputs = tokenizer(
            batch_texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            autocast = torch.autocast(device_type=device, dtype=dtype) if device != "cpu" else nullcontext()
            with autocast:
                outputs = model(**inputs)

        probs = torch.sigmoid(outputs.logits).float().cpu().numpy()

        for prob_row in probs:
            detected = [
                ASPECT_LABELS[j]
                for j in range(len(ASPECT_LABELS))
                if prob_row[j] >= threshold
            ]
            all_predictions.append(detected)
            all_probabilities.append({
                ASPECT_LABELS[j]: round(float(prob_row[j]), 4)
                for j in range(len(ASPECT_LABELS))
            })

        del inputs, outputs, probs

    return all_predictions, all_probabilities


def predict_sentiments(
    pairs: list[tuple[str, str]],
    tokenizer: AutoTokenizer,
    model: AutoModelForSequenceClassification,
    device: str,
    dtype: torch.dtype,
    batch_size: int,
) -> list[tuple[str, float]]:
    results: list[tuple[str, float]] = []

    for i in range(0, len(pairs), batch_size):
        batch_pairs = pairs[i:i + batch_size]
        texts_a = [p[0] for p in batch_pairs]
        texts_b = [p[1] for p in batch_pairs]

        inputs = tokenizer(
            texts_a,
            texts_b,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            autocast = torch.autocast(device_type=device, dtype=dtype) if device != "cpu" else nullcontext()
            with autocast:
                outputs = model(**inputs)

        probs = torch.softmax(outputs.logits, dim=-1).float().cpu().numpy()

        for prob_row in probs:
            pred_idx = int(prob_row.argmax())
            confidence = float(prob_row[pred_idx])
            results.append((SENTIMENT_LABELS[pred_idx], confidence))

        del inputs, outputs, probs

    return results


def run_feedbacks_pipeline(
    db: Any,
    aspect_tokenizer: AutoTokenizer,
    aspect_model: AutoModelForSequenceClassification,
    sentiment_tokenizer: AutoTokenizer,
    sentiment_model: AutoModelForSequenceClassification,
    device: str,
    dtype: torch.dtype,
    batch_size: int,
    threshold: float,
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {"processed": 0, "written": 0, "skipped": 0, "zero_aspect": 0}

    unprocessed_ids = get_pending_feedback_ids(db, threshold)
    if not unprocessed_ids:
        print("[FEEDBACKS] No unprocessed documents found.")
        return stats

    id_list = list(unprocessed_ids)
    print(f"[FEEDBACKS] Processing {len(id_list)} documents (Stage 1 + Stage 2)...")

    for i in range(0, len(id_list), BATCH_FETCH_SIZE):
        batch_ids = id_list[i:i + BATCH_FETCH_SIZE]
        docs = list(db[CLEANED_FEEDBACKS].find(
            {
                "_id": {"$in": batch_ids},
                "cleaning_status": "clean",
                "cleaned_text": {"$exists": True, "$ne": ""},
            },
            {
                "_id": 1, "content_id": 1, "entity_name": 1,
                "cleaned_text": 1, "feedback_timestamp": 1, "platform": 1,
                "rating": 1, "source_fingerprint": 1,
            },
        ))

        stats["skipped"] += len(batch_ids) - len(docs)
        if not docs:
            continue

        valid_docs = [d for d in docs if d.get("cleaned_text") and d["cleaned_text"].strip()]
        stats["skipped"] += len(docs) - len(valid_docs)

        if not valid_docs:
            continue

        texts = [d["cleaned_text"] for d in valid_docs]

        print(f"  Stage 1: Detecting aspects for {len(texts)} documents...")
        all_aspects, all_probs = predict_aspects(
            texts, aspect_tokenizer, aspect_model, device, dtype, threshold, batch_size,
        )

        all_pairs: list[tuple[str, str]] = []
        pair_to_doc: list[int] = []
        doc_aspects: dict[int, list[str]] = {}

        for doc_idx, aspects in enumerate(all_aspects):
            doc_aspects[doc_idx] = aspects
            if aspects:
                for aspect in aspects:
                    all_pairs.append((texts[doc_idx], aspect))
                    pair_to_doc.append(doc_idx)

        pair_results: list[tuple[str, float]] = []
        if all_pairs:
            print(f"  Stage 2: Classifying sentiment for {len(all_pairs)} pairs...")
            pair_results = predict_sentiments(
                all_pairs, sentiment_tokenizer, sentiment_model, device, dtype, batch_size,
            )

        doc_sentiments: dict[int, list[dict]] = {idx: [] for idx in range(len(valid_docs))}
        for pair_idx, (sentiment, confidence) in enumerate(pair_results):
            doc_idx = pair_to_doc[pair_idx]
            aspect_name = doc_aspects[doc_idx][
                len(doc_sentiments[doc_idx])
            ]
            doc_sentiments[doc_idx].append({
                "aspect": aspect_name,
                "sentiment": sentiment,
                "confidence": round(confidence, 4),
            })

        if dry_run:
            stats["processed"] += len(valid_docs)
            for doc_idx in range(len(valid_docs)):
                if not doc_aspects[doc_idx]:
                    stats["zero_aspect"] += 1
            continue

        ops: list[ReplaceOne] = []
        now = datetime.now()

        for doc_idx, doc in enumerate(valid_docs):
            aspects = doc_aspects[doc_idx]
            sentiments = doc_sentiments[doc_idx]

            if not aspects:
                stats["zero_aspect"] += 1

            output_doc = {
                "feedback_id": doc["_id"],
                "source_fingerprint": doc.get("source_fingerprint"),
                "processing_fingerprint": _processing_fingerprint(
                    doc, pipeline="feedbacks", threshold=threshold
                ),
                "content_id": doc.get("content_id"),
                "platform": doc.get("platform", "foodpanda"),
                "entity_name": doc.get("entity_name", ""),
                "feedback_timestamp": doc.get("feedback_timestamp"),
                "raw_text": doc["cleaned_text"],
                "aspect_count": len(aspects),
                "aspect_sentiments": sentiments,
                "processed_at": now,
            }

            ops.append(ReplaceOne(
                {"_id": doc["_id"]},
                output_doc,
                upsert=True,
            ))

        if ops:
            result = db[OUTPUT_FEEDBACKS].bulk_write(ops, ordered=False)
            written = (result.upserted_count or 0) + (result.modified_count or 0)
            stats["written"] += written

        stats["processed"] += len(valid_docs)
        print(f"  Batch {i // BATCH_FETCH_SIZE + 1}: processed {len(valid_docs)}, written {len(ops)}")

    print(f"\n[FEEDBACKS] Done: {stats['processed']} processed, "
          f"{stats['written']} written, {stats['skipped']} skipped, "
          f"{stats['zero_aspect']} zero-aspect")
    return stats


def run_contents_pipeline(
    db: Any,
    aspect_tokenizer: AutoTokenizer,
    aspect_model: AutoModelForSequenceClassification,
    device: str,
    dtype: torch.dtype,
    batch_size: int,
    threshold: float,
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {"processed": 0, "written": 0, "skipped": 0}

    unprocessed_ids = get_pending_content_ids(db, threshold)
    if not unprocessed_ids:
        print("[CONTENTS] No unprocessed documents found.")
        return stats

    id_list = list(unprocessed_ids)
    print(f"[CONTENTS] Processing {len(id_list)} Facebook posts (Stage 1 only)...")

    for i in range(0, len(id_list), BATCH_FETCH_SIZE):
        batch_ids = id_list[i:i + BATCH_FETCH_SIZE]
        docs = list(db[CLEANED_CONTENTS].find(
            {
                "_id": {"$in": batch_ids},
                "platform": "facebook",
                "cleaning_status": "clean",
                "cleaned_text": {"$exists": True, "$ne": ""},
            },
            {
                "_id": 1, "entity_name": 1, "cleaned_text": 1,
                "post_timestamp": 1, "platform": 1,
                "source_fingerprint": 1,
                "positivity_ratio": 1, "negativity_ratio": 1,
                "total_reactions": 1, "like_count": 1, "love_count": 1,
                "haha_count": 1, "sad_count": 1, "angry_count": 1, "care_count": 1,
                "wow_count": 1, "shares_count": 1, "comments_count": 1,
            },
        ))

        stats["skipped"] += len(batch_ids) - len(docs)
        if not docs:
            continue

        valid_docs = [d for d in docs if d.get("cleaned_text") and d["cleaned_text"].strip()]
        stats["skipped"] += len(docs) - len(valid_docs)

        if not valid_docs:
            continue

        texts = [d["cleaned_text"] for d in valid_docs]

        print(f"  Stage 1: Detecting aspects for {len(texts)} posts...")
        all_aspects, all_probs = predict_aspects(
            texts, aspect_tokenizer, aspect_model, device, dtype, threshold, batch_size,
        )

        if dry_run:
            stats["processed"] += len(valid_docs)
            continue

        ops: list[ReplaceOne] = []
        now = datetime.now()

        for doc_idx, doc in enumerate(valid_docs):
            output_doc = {
                "content_id": doc["_id"],
                "source_fingerprint": doc.get("source_fingerprint"),
                "processing_fingerprint": _processing_fingerprint(
                    doc, pipeline="contents", threshold=threshold
                ),
                "platform": "facebook",
                "entity_name": doc.get("entity_name", ""),
                "post_timestamp": doc.get("post_timestamp"),
                "post_text": doc["cleaned_text"],
                "promoted_aspects": all_aspects[doc_idx],
                "aspect_probabilities": all_probs[doc_idx],
                "total_reactions": doc.get("total_reactions"),
                "like_count": doc.get("like_count"),
                "love_count": doc.get("love_count"),
                "haha_count": doc.get("haha_count"),
                "sad_count": doc.get("sad_count"),
                "angry_count": doc.get("angry_count"),
                "care_count": doc.get("care_count"),
                "wow_count": doc.get("wow_count"),
                "shares_count": doc.get("shares_count"),
                "comments_count": doc.get("comments_count"),
                "positivity_ratio": doc.get("positivity_ratio"),
                "negativity_ratio": doc.get("negativity_ratio"),
                "processed_at": now,
            }

            ops.append(ReplaceOne(
                {"_id": doc["_id"]},
                output_doc,
                upsert=True,
            ))

        if ops:
            result = db[OUTPUT_CONTENTS].bulk_write(ops, ordered=False)
            written = (result.upserted_count or 0) + (result.modified_count or 0)
            stats["written"] += written

        stats["processed"] += len(valid_docs)
        print(f"  Batch {i // BATCH_FETCH_SIZE + 1}: processed {len(valid_docs)}, written {len(ops)}")

    print(f"\n[CONTENTS] Done: {stats['processed']} processed, "
          f"{stats['written']} written, {stats['skipped']} skipped")
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Burmese ABSA Inference Pipeline — "
                    "Two-stage aspect-based sentiment analysis on cleaned text",
    )
    parser.add_argument(
        "--pipeline",
        choices=["feedbacks", "contents", "both"],
        default="both",
        help="Which pipeline to run (default: both)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Model inference batch size (default: auto based on device)",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu"],
        default="auto",
        help="Compute device (default: auto-detect)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Aspect detection probability threshold (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--models-dir",
        type=str,
        default=None,
        help=f"Local models directory (default: {DEFAULT_MODELS_DIR}). "
             f"Falls back to HuggingFace Hub if not found.",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Drop output collections and reprocess all documents",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview processing without writing to MongoDB",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show pipeline processing status and exit",
    )
    return parser


def show_status(db: Any) -> None:
    print(f"\n{'=' * 60}")
    print("ABSA PIPELINE STATUS")
    print(f"{'=' * 60}")

    for label, src, out, extra_filter in [
        ("FEEDBACKS (Foodpanda Reviews → Stage 1 + Stage 2)",
         CLEANED_FEEDBACKS, OUTPUT_FEEDBACKS,
         {"cleaning_status": "clean", "cleaned_text": {"$exists": True, "$ne": ""}}),
        ("CONTENTS (Facebook Posts → Stage 1 only)",
         CLEANED_CONTENTS, OUTPUT_CONTENTS,
         {"platform": "facebook", "cleaning_status": "clean",
          "cleaned_text": {"$exists": True, "$ne": ""}}),
    ]:
        source_count = db[src].count_documents(extra_filter)
        output_count = db[out].count_documents({})
        unprocessed = source_count - output_count

        print(f"\n[{label}]")
        print(f"  Eligible source docs:  {source_count}")
        print(f"  Processed:             {output_count}")
        print(f"  Unprocessed:           {max(0, unprocessed)}")

        if out == OUTPUT_FEEDBACKS and output_count > 0:
            zero_aspect = db[out].count_documents({"aspect_count": 0})
            print(f"  Zero-aspect docs:     {zero_aspect}")

            pipeline = [
                {"$unwind": "$aspect_sentiments"},
                {"$group": {
                    "_id": "$aspect_sentiments.aspect",
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
            ]
            aspect_dist = list(db[out].aggregate(pipeline))
            if aspect_dist:
                print(f"  Aspect distribution:")
                for item in aspect_dist:
                    print(f"    {item['_id']}: {item['count']}")

        if out == OUTPUT_CONTENTS and output_count > 0:
            pipeline = [
                {"$unwind": "$promoted_aspects"},
                {"$group": {
                    "_id": "$promoted_aspects",
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
            ]
            aspect_dist = list(db[out].aggregate(pipeline))
            if aspect_dist:
                print(f"  Promoted aspect distribution:")
                for item in aspect_dist:
                    print(f"    {item['_id']}: {item['count']}")

    print(f"\n{'=' * 60}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.status:
        client, db = get_db()
        try:
            show_status(db)
        finally:
            client.close()
        return

    device_str, dtype, default_batch = detect_device()

    if args.device != "auto":
        device_str = args.device
        if device_str == "cuda" and not torch.cuda.is_available():
            print("[WARN] CUDA requested but not available, falling back to CPU")
            device_str = "cpu"
        if device_str == "cuda":
            dtype = torch.bfloat16
            default_batch = GPU_BATCH_SIZE
        else:
            dtype = torch.float32
            default_batch = CPU_BATCH_SIZE

    batch_size = args.batch_size or default_batch

    print(f"\n{'=' * 60}")
    print("BURMESE ABSA INFERENCE PIPELINE")
    print(f"{'=' * 60}")
    print(f"  Device:        {device_str}")
    print(f"  Precision:     {dtype}")
    print(f"  Batch size:    {batch_size}")
    print(f"  Pipeline:      {args.pipeline}")
    print(f"  Threshold:     {args.threshold}")
    print(f"  Reprocess:     {args.reprocess}")
    print(f"  Dry-run:       {args.dry_run}")
    print(f"{'=' * 60}\n")

    models_dir: Path | None = None
    if args.models_dir is not None:
        models_dir = Path(args.models_dir) if args.models_dir else None
    elif DEFAULT_MODELS_DIR.exists():
        models_dir = DEFAULT_MODELS_DIR
        print(f"Using local models: {models_dir}")
    else:
        print("No local models found, will download from HuggingFace Hub.\n")

    client, db = get_db()

    try:
        if args.reprocess:
            print("[WARN] Dropping output collections for reprocessing...")
            if args.pipeline in ("feedbacks", "both"):
                db[OUTPUT_FEEDBACKS].drop()
                print(f"  Dropped {OUTPUT_FEEDBACKS}")
            if args.pipeline in ("contents", "both"):
                db[OUTPUT_CONTENTS].drop()
                print(f"  Dropped {OUTPUT_CONTENTS}")
            print()

        feedback_stats: dict[str, int] = {}
        contents_stats: dict[str, int] = {}
        aspect_tokenizer = None
        aspect_model = None

        if args.pipeline in ("feedbacks", "both"):
            aspect_source = _resolve_model_path(models_dir, ASPECT_MODEL_FOLDER, ASPECT_MODEL_ID)
            print(f"Loading aspect detection model...")
            aspect_tokenizer = AutoTokenizer.from_pretrained(aspect_source)
            aspect_model = AutoModelForSequenceClassification.from_pretrained(
                aspect_source, torch_dtype=dtype,
            ).to(device_str)
            aspect_model.eval()

            sentiment_source = _resolve_model_path(models_dir, SENTIMENT_MODEL_FOLDER, SENTIMENT_MODEL_ID)
            print(f"Loading sentiment model...")
            sentiment_tokenizer = AutoTokenizer.from_pretrained(sentiment_source)
            sentiment_model = AutoModelForSequenceClassification.from_pretrained(
                sentiment_source, torch_dtype=dtype,
            ).to(device_str)
            sentiment_model.eval()

            print()
            feedback_stats = run_feedbacks_pipeline(
                db,
                aspect_tokenizer, aspect_model,
                sentiment_tokenizer, sentiment_model,
                device_str, dtype, batch_size, args.threshold,
                dry_run=args.dry_run,
            )

        if args.pipeline in ("contents", "both"):
            if aspect_model is None:
                aspect_source = _resolve_model_path(models_dir, ASPECT_MODEL_FOLDER, ASPECT_MODEL_ID)
                print(f"Loading aspect detection model...")
                aspect_tokenizer = AutoTokenizer.from_pretrained(aspect_source)
                aspect_model = AutoModelForSequenceClassification.from_pretrained(
                    aspect_source, torch_dtype=dtype,
                ).to(device_str)
                aspect_model.eval()

            print()
            contents_stats = run_contents_pipeline(
                db,
                aspect_tokenizer, aspect_model,
                device_str, dtype, batch_size, args.threshold,
                dry_run=args.dry_run,
            )

        if args.dry_run:
            print(f"\n[DRY RUN] No data was written to MongoDB.")
        else:
            print(f"\n{'=' * 60}")
            print("PIPELINE SUMMARY")
            print(f"{'=' * 60}")
            if feedback_stats:
                print(f"  Feedbacks:  {feedback_stats['processed']} processed, "
                      f"{feedback_stats['written']} written, "
                      f"{feedback_stats.get('zero_aspect', 0)} zero-aspect")
            if contents_stats:
                print(f"  Contents:   {contents_stats['processed']} processed, "
                      f"{contents_stats['written']} written")
            print(f"{'=' * 60}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
