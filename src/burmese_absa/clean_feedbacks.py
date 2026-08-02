"""
Burmese Text Cleaning Pipeline
──────────────────────────────
Reads raw text from contents and feedbacks collections, applies
Burmese-aware text cleaning, and writes cleaned output to new collections.

Collections:
  - contents    → cleaned_contents   (field: title_or_post)
  - feedbacks   → cleaned_feedbacks  (field: raw_text)

Usage:
  python clean_feedbacks.py                           # Clean unprocessed docs
  python clean_feedbacks.py --collection feedbacks    # One collection only
  python clean_feedbacks.py --reprocess               # Drop and re-clean all
  python clean_feedbacks.py --dry-run                 # Preview without writing
  python clean_feedbacks.py --status                  # Show cleaning stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from typing import Any

from pymongo import MongoClient, UpdateOne

from .mongo_config import MONGO_URI

# Windows terminal encoding fix for Burmese output
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

# ==========================================
# Configuration
# ==========================================
DB_NAME = "feedback_analytics"

CONTENTS_COLLECTION = "contents"
FEEDBACKS_COLLECTION = "feedbacks"
CLEANED_CONTENTS_COLLECTION = "cleaned_contents"
CLEANED_FEEDBACKS_COLLECTION = "cleaned_feedbacks"

BATCH_SIZE = 500
MIN_CLEAN_LENGTH = 3

CONTENT_SOURCE_FIELDS = (
    "title_or_post",
    "entity_name",
    "source_type",
    "post_timestamp",
    "reactions_breakdown",
    "grouped_reactions",
    "total_shares",
    "total_comments",
)
FEEDBACK_SOURCE_FIELDS = (
    "raw_text",
    "content_id",
    "entity_name",
    "source_type",
    "feedback_date",
    "rating",
)

# ==========================================
# Zawgyi Detection (simplified heuristic)
# ==========================================
# Zawgyi uses non-standard code points that overlap with Myanmar Unicode.
# This is a simplified detector; for production, use myanmar-tools package.
#
# Zawgyi-specific ranges that don't exist in standard Unicode Myanmar:
# - U+104E (၎) used differently
# - Certain combining marks used in Zawgyi-only patterns
#
# For accurate detection, install: pip install myanmar-tools

try:
    from google_myanmar_tools import ZawgyiDetector
    _zawgyi_detector = ZawgyiDetector()
    HAS_MYANMAR_TOOLS = True
except ImportError:
    _zawgyi_detector = None
    HAS_MYANMAR_TOOLS = False

# Fallback: Zawgyi indicator patterns
_ZAWGYI_INDICATORS = re.compile(
    r'[\u104E\u105A\u105B\u105C\u105D\u105E\u105F\u1060\u1061'
    r'\u1062\u1063\u1064\u1065\u1066\u1067\u1068\u1069\u106A'
    r'\u106B\u106C\u106D\u106E\u106F\u1070\u1071\u1072\u1073'
    r'\u1074\u1075\u1076\u1077\u1078\u1079\u107A\u107B\u107C'
    r'\u107D\u107E\u107F\u1080\u1081\u1082\u1083\u1084\u1085'
    r'\u1086\u1087\u1088\u1089\u108A\u108B\u108C\u108D\u108E'
    r'\u108F\u1090\u1091\u1092\u1093\u1094\u1095\u1096\u1097]'
)

# ==========================================
# Zawgyi to Unicode Conversion (simplified)
# ==========================================
# For production use, use myanmar-tools or zg2uni converters.
# This is a minimal mapping for common Zawgyi characters.

_ZAWGYI_TO_UNI: dict[str, str] = {
    # Common Zawgyi-specific characters → Unicode equivalents
    # This is incomplete; use myanmar-tools for full conversion
    '\u104E': '၎',  # Same codepoint, different usage
}

def _zawgyi_to_unicode_fallback(text: str) -> str:
    """Minimal Zawgyi→Unicode conversion. Use myanmar-tools for production."""
    result = text
    for zg, uni in _ZAWGYI_TO_UNI.items():
        result = result.replace(zg, uni)
    return result

# ==========================================
# Noise Removal Patterns
# ==========================================
_URL_RE = re.compile(
    r'https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.(com|org|net|io|mm|co|gov|edu|info)(/[^\s]*)?',
    re.IGNORECASE
)
_MENTION_RE = re.compile(r'@[a-zA-Z0-9_]+')
_HASHTAG_MARKER_RE = re.compile(r'#(?=\S)')  # Remove # but keep text
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_HTML_ENTITY_RE = re.compile(r'&[a-zA-Z]+;|&#\d+;|&#x[0-9a-fA-F]+;')
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]')
_ZERO_WIDTH_RE = re.compile(r'[\u200B-\u200F\u2028-\u202F\uFEFF]')
_REPEATED_CHAR_RE = re.compile(r'(.)\1{3,}')  # 4+ repeated chars

# Emoji ranges (simplified, covers common emoji blocks)
_EMOJI_RE = re.compile(
    r'[\U0001F600-\U0001F64F'  # Emoticons
    r'\U0001F300-\U0001F5FF'   # Misc Symbols and Pictographs
    r'\U0001F680-\U0001F6FF'   # Transport and Map
    r'\U0001F700-\U0001F77F'   # Alchemical Symbols
    r'\U0001F780-\U0001F7FF'   # Geometric Shapes Extended
    r'\U0001F800-\U0001F8FF'   # Supplemental Arrows-C
    r'\U0001F900-\U0001F9FF'   # Supplemental Symbols and Pictographs
    r'\U0001FA00-\U0001FA6F'   # Chess Symbols
    r'\U0001FA70-\U0001FAFF'   # Symbols and Pictographs Extended-A
    r'\U00002702-\U000027B0'   # Dingbats
    r'\U000024C2-\U0001F251'
    r'\U0001f926-\U0001f937'
    r'\U00010000-\U0010ffff'
    r'\u2600-\u2B55'
    r'\u200d'
    r'\u23cf'
    r'\u23e9'
    r'\u231a'
    r'\ufe0f'
    r'\u3030'
    r'\u00a9\u00ae]+',
    flags=re.UNICODE
)

# ==========================================
# Burmese Digit Translation
# ==========================================
_BURMESE_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")

# ==========================================
# Myanmar Unicode Detection
# ==========================================
_MYANMAR_RANGE_RE = re.compile(r'[\u1000-\u109F\uAA60-\uAA7F\uA9E0-\uA9FF]')
_LATIN_RANGE_RE = re.compile(r'[a-zA-Z]')

# ==========================================
# Cleaning Functions
# ==========================================

def detect_encoding(text: str) -> str:
    """Detect if text is Zawgyi or Unicode encoded."""
    if not text:
        return "unicode"

    if HAS_MYANMAR_TOOLS and _zawgyi_detector:
        score = _zawgyi_detector.get_zawgyi_probability(text)
        return "zawgyi" if score > 0.5 else "unicode"

    # Fallback: check for Zawgyi-specific indicator patterns
    if _ZAWGYI_INDICATORS.search(text):
        return "zawgyi"

    return "unicode"


def convert_zawgyi_to_unicode(text: str, encoding: str) -> str:
    """Convert Zawgyi text to Unicode if needed."""
    if encoding != "zawgyi":
        return text

    if HAS_MYANMAR_TOOLS:
        # myanmar-tools provides converter
        try:
            from google_myanmar_tools import ZawgyiConverter
            converter = ZawgyiConverter()
            return converter.zawgyi_to_unicode(text)
        except ImportError:
            pass

    return _zawgyi_to_unicode_fallback(text)


def normalize_unicode(text: str) -> str:
    """Apply NFC normalization and remove zero-width characters."""
    text = unicodedata.normalize('NFC', text)
    text = _ZERO_WIDTH_RE.sub('', text)
    return text


def remove_noise(text: str) -> str:
    """Remove social media noise: URLs, mentions, hashtags, emojis, HTML."""
    text = _URL_RE.sub('', text)
    text = _MENTION_RE.sub('', text)
    text = _HASHTAG_MARKER_RE.sub('', text)  # Keep text after #
    text = _HTML_TAG_RE.sub('', text)
    text = _HTML_ENTITY_RE.sub('', text)
    text = _EMOJI_RE.sub('', text)
    text = _CONTROL_CHARS_RE.sub('', text)
    text = _REPEATED_CHAR_RE.sub(r'\1\1', text)  # Collapse to max 2 repeats
    return text


def normalize_text(text: str) -> str:
    """Normalize digits, whitespace, and case."""
    text = text.translate(_BURMESE_DIGITS)
    text = re.sub(r'\s+', ' ', text).strip()
    # Lowercase only Latin characters (Burmese has no case)
    text = ''.join(c.lower() if c.isascii() and c.isalpha() else c for c in text)
    return text


def detect_language(text: str) -> str:
    """Detect language based on character ratios."""
    if not text:
        return "empty"

    myanmar_chars = len(_MYANMAR_RANGE_RE.findall(text))
    latin_chars = len(_LATIN_RANGE_RE.findall(text))
    total_relevant = myanmar_chars + latin_chars

    if total_relevant == 0:
        return "unknown"

    myanmar_ratio = myanmar_chars / total_relevant
    latin_ratio = latin_chars / total_relevant

    if myanmar_ratio > 0.7:
        return "my"
    elif latin_ratio > 0.7:
        return "en"
    else:
        return "mixed"


def quality_gate(text: str) -> str:
    """Check if cleaned text meets quality standards."""
    if not text or len(text.strip()) < MIN_CLEAN_LENGTH:
        return "filtered"

    # Check if text is purely numeric/punctuation
    alpha_chars = sum(1 for c in text if c.isalpha() or _MYANMAR_RANGE_RE.match(c))
    if alpha_chars == 0:
        return "filtered"

    return "clean"


def clean_text(raw_text: str | None) -> dict[str, Any]:
    """
    Apply the full 5-stage cleaning pipeline to raw text.

    Returns dict with:
        - cleaned_text: str
        - text_language: str ("my", "en", "mixed", "unknown", "empty")
        - encoding_source: str ("unicode", "zawgyi")
        - cleaning_status: str ("clean", "filtered", "empty")
    """
    if not raw_text or not raw_text.strip():
        return {
            "cleaned_text": "",
            "text_language": "empty",
            "encoding_source": "unicode",
            "cleaning_status": "empty",
        }

    text = raw_text

    # Stage 1: Encoding Detection & Unicode Normalization
    encoding = detect_encoding(text)
    text = convert_zawgyi_to_unicode(text, encoding)
    text = normalize_unicode(text)

    # Stage 2: Noise Removal
    text = remove_noise(text)

    # Stage 3: Text Normalization
    text = normalize_text(text)

    # Stage 4: Language Detection
    language = detect_language(text)

    # Stage 5: Quality Gate
    status = quality_gate(text)

    return {
        "cleaned_text": text,
        "text_language": language,
        "encoding_source": encoding,
        "cleaning_status": status,
    }


# ==========================================
# MongoDB Operations
# ==========================================

def get_db(mongo_uri: str | None = None):
    """Connect to MongoDB."""
    try:
        resolved_uri = mongo_uri or MONGO_URI
        client = MongoClient(resolved_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
    except Exception as e:
        print(f"[ERROR] MongoDB not reachable at {mongo_uri or MONGO_URI}: {e}")
        print("[HINT] Start MongoDB first: docker-compose up -d")
        raise
    return client[DB_NAME]


def _fingerprint_value(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: item.isoformat()
        if isinstance(item, datetime)
        else str(item),
    )


def source_fingerprint(doc: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Fingerprint fields that affect the cleaned or exported representation."""
    payload = {field: doc.get(field) for field in fields}
    return hashlib.sha256(_fingerprint_value(payload).encode("utf-8")).hexdigest()


def get_unprocessed_ids(original_col: str, cleaned_col: str, db) -> set[str]:
    """
    Return missing or stale source IDs.

    Older cleaned documents have no ``source_fingerprint`` and are refreshed
    once. This fixes the previous ID-only check, which never propagated edits
    or engagement updates after the first cleaning pass.
    """
    field_map = {
        CONTENTS_COLLECTION: CONTENT_SOURCE_FIELDS,
        FEEDBACKS_COLLECTION: FEEDBACK_SOURCE_FIELDS,
    }
    fields = field_map.get(original_col)
    if fields is None:
        original_ids = {
            doc["_id"] for doc in db[original_col].find({}, {"_id": 1})
        }
        cleaned_ids = {
            doc["_id"] for doc in db[cleaned_col].find({}, {"_id": 1})
        }
        return original_ids - cleaned_ids

    cleaned_fingerprints = {
        doc["_id"]: doc.get("source_fingerprint")
        for doc in db[cleaned_col].find(
            {}, {"_id": 1, "source_fingerprint": 1}
        )
    }
    projection = {"_id": 1, **{field: 1 for field in fields}}
    return {
        doc["_id"]
        for doc in db[original_col].find({}, projection)
        if cleaned_fingerprints.get(doc["_id"])
        != source_fingerprint(doc, fields)
    }


def process_contents(unprocessed_ids: set[str], db, dry_run: bool = False) -> dict[str, int]:
    """Clean and store contents text."""
    stats = {"processed": 0, "clean": 0, "filtered": 0, "empty": 0, "zawgyi": 0}

    if not unprocessed_ids:
        return stats

    print(f"[CONTENTS] Processing {len(unprocessed_ids)} unprocessed documents...")

    # Batch fetch
    id_list = list(unprocessed_ids)
    for i in range(0, len(id_list), BATCH_SIZE):
        batch_ids = id_list[i:i + BATCH_SIZE]
        docs = list(db[CONTENTS_COLLECTION].find(
            {"_id": {"$in": batch_ids}},
            {
                "_id": 1, "title_or_post": 1, "entity_name": 1,
                "source_type": 1, "post_timestamp": 1,
                "reactions_breakdown": 1, "grouped_reactions": 1,
                "total_shares": 1, "total_comments": 1,
            }
        ))

        if dry_run:
            stats["processed"] += len(docs)
            continue

        ops = []
        for doc in docs:
            raw_text = doc.get("title_or_post", "")
            result = clean_text(raw_text)

            # Detect platform from source_type
            source_type = doc.get("source_type", "")
            if source_type == "Platform":
                platform = "foodpanda"
            else:
                platform = "facebook"

            cleaned_doc = {
                "_id": doc["_id"],
                "source_id": doc["_id"],
                "source_fingerprint": source_fingerprint(
                    doc, CONTENT_SOURCE_FIELDS
                ),
                "entity_name": doc.get("entity_name", ""),
                "platform": platform,
                "post_timestamp": doc.get("post_timestamp"),
                **result,
                "cleaned_at": datetime.now(),
            }

            # Add engagement metrics for Facebook posts
            if platform == "facebook":
                reactions = doc.get("reactions_breakdown", {}) or {}
                grouped = doc.get("grouped_reactions", {}) or {}

                cleaned_doc["total_reactions"] = reactions.get("total")
                cleaned_doc["like_count"] = reactions.get("like")
                cleaned_doc["love_count"] = reactions.get("love")
                cleaned_doc["haha_count"] = reactions.get("haha")
                cleaned_doc["sad_count"] = reactions.get("sad")
                cleaned_doc["angry_count"] = reactions.get("angry")
                cleaned_doc["care_count"] = reactions.get("care")
                cleaned_doc["wow_count"] = reactions.get("wow")
                cleaned_doc["shares_count"] = doc.get("total_shares")
                cleaned_doc["comments_count"] = doc.get("total_comments")
                cleaned_doc["positivity_ratio"] = grouped.get("positivity_ratio")
                cleaned_doc["negativity_ratio"] = grouped.get("negativity_ratio")

            # Upsert into cleaned collection
            ops.append(UpdateOne(
                {"_id": doc["_id"]},
                {"$set": cleaned_doc},
                upsert=True
            ))

            stats["processed"] += 1
            stats[result["cleaning_status"]] += 1
            if result["encoding_source"] == "zawgyi":
                stats["zawgyi"] += 1

        if ops:
            db[CLEANED_CONTENTS_COLLECTION].bulk_write(ops, ordered=False)
            print(f"  Batch {i // BATCH_SIZE + 1}: wrote {len(ops)} docs")

    return stats


def process_feedbacks(unprocessed_ids: set[str], db, dry_run: bool = False) -> dict[str, int]:
    """Clean and store feedbacks text."""
    stats = {"processed": 0, "clean": 0, "filtered": 0, "empty": 0, "zawgyi": 0}

    if not unprocessed_ids:
        return stats

    print(f"[FEEDBACKS] Processing {len(unprocessed_ids)} unprocessed documents...")

    # Batch fetch
    id_list = list(unprocessed_ids)
    for i in range(0, len(id_list), BATCH_SIZE):
        batch_ids = id_list[i:i + BATCH_SIZE]
        docs = list(db[FEEDBACKS_COLLECTION].find(
            {"_id": {"$in": batch_ids}},
            {
                "_id": 1, "raw_text": 1, "content_id": 1,
                "entity_name": 1, "source_type": 1,
                "feedback_date": 1, "rating": 1
            }
        ))

        if dry_run:
            stats["processed"] += len(docs)
            continue

        ops = []
        for doc in docs:
            raw_text = doc.get("raw_text", "")
            result = clean_text(raw_text)

            # Detect platform from _id or content_id prefix
            doc_id = str(doc.get("_id", ""))
            content_id = str(doc.get("content_id", ""))
            if doc_id.startswith("fp_") or content_id.startswith("fp_"):
                platform = "foodpanda"
            elif doc_id.startswith("fb_") or content_id.startswith("fb_"):
                platform = "facebook"
            else:
                platform = "unknown"

            # Handle rating: convert string "None" to actual None
            rating = doc.get("rating")
            if isinstance(rating, str) and rating.lower() == "none":
                rating = None

            cleaned_doc = {
                "_id": doc["_id"],
                "source_id": doc["_id"],
                "source_fingerprint": source_fingerprint(
                    doc, FEEDBACK_SOURCE_FIELDS
                ),
                "content_id": doc.get("content_id"),
                "entity_name": doc.get("entity_name", ""),
                "platform": platform,
                "feedback_timestamp": doc.get("feedback_date"),
                "rating": rating,
                **result,
                "cleaned_at": datetime.now(),
            }

            # Upsert into cleaned collection
            ops.append(UpdateOne(
                {"_id": doc["_id"]},
                {"$set": cleaned_doc},
                upsert=True
            ))

            stats["processed"] += 1
            stats[result["cleaning_status"]] += 1
            if result["encoding_source"] == "zawgyi":
                stats["zawgyi"] += 1

        if ops:
            db[CLEANED_FEEDBACKS_COLLECTION].bulk_write(ops, ordered=False)
            print(f"  Batch {i // BATCH_SIZE + 1}: wrote {len(ops)} docs")

    return stats


def show_status(db):
    """Display cleaning statistics for both collections."""
    print("\n" + "=" * 60)
    print("CLEANING STATUS")
    print("=" * 60)

    for orig, cleaned in [
        (CONTENTS_COLLECTION, CLEANED_CONTENTS_COLLECTION),
        (FEEDBACKS_COLLECTION, CLEANED_FEEDBACKS_COLLECTION),
    ]:
        orig_count = db[orig].count_documents({})
        cleaned_count = db[cleaned].count_documents({})
        unprocessed = orig_count - cleaned_count

        print(f"\n[{orig.upper()}]")
        print(f"  Original docs:     {orig_count}")
        print(f"  Cleaned docs:      {cleaned_count}")
        print(f"  Unprocessed:       {unprocessed}")

        if cleaned_count > 0:
            clean_status = db[cleaned].count_documents({"cleaning_status": "clean"})
            filtered_status = db[cleaned].count_documents({"cleaning_status": "filtered"})
            empty_status = db[cleaned].count_documents({"cleaning_status": "empty"})
            zawgyi_count = db[cleaned].count_documents({"encoding_source": "zawgyi"})

            print(f"  Clean (usable):    {clean_status}")
            print(f"  Filtered:          {filtered_status}")
            print(f"  Empty:             {empty_status}")
            print(f"  Zawgyi detected:   {zawgyi_count}")

    print("\n" + "=" * 60)


# ==========================================
# CLI
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Burmese Text Cleaning Pipeline")
    parser.add_argument(
        "--collection",
        choices=["contents", "feedbacks", "both"],
        default="both",
        help="Which collection to clean (default: both)"
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Drop cleaned collections and re-clean all documents"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview processing without writing to MongoDB"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show cleaning statistics and exit"
    )
    args = parser.parse_args()

    db = get_db()

    if args.status:
        show_status(db)
        return

    if args.reprocess:
        print("[WARN] Dropping cleaned collections for reprocessing...")
        if args.collection in ("contents", "both"):
            db[CLEANED_CONTENTS_COLLECTION].drop()
            print(f"  Dropped {CLEANED_CONTENTS_COLLECTION}")
        if args.collection in ("feedbacks", "both"):
            db[CLEANED_FEEDBACKS_COLLECTION].drop()
            print(f"  Dropped {CLEANED_FEEDBACKS_COLLECTION}")

    # Check myanmar-tools availability
    if not HAS_MYANMAR_TOOLS:
        print("[WARN] myanmar-tools not installed. Using fallback Zawgyi detection.")
        print("[HINT] Install for better accuracy: pip install myanmar-tools")

    total_stats = {"processed": 0, "clean": 0, "filtered": 0, "empty": 0, "zawgyi": 0}

    if args.collection in ("contents", "both"):
        unprocessed = get_unprocessed_ids(CONTENTS_COLLECTION, CLEANED_CONTENTS_COLLECTION, db)
        if not unprocessed:
            print(f"[CONTENTS] No unprocessed documents found.")
        else:
            stats = process_contents(unprocessed, db, dry_run=args.dry_run)
            for k in total_stats:
                total_stats[k] += stats[k]

    if args.collection in ("feedbacks", "both"):
        unprocessed = get_unprocessed_ids(FEEDBACKS_COLLECTION, CLEANED_FEEDBACKS_COLLECTION, db)
        if not unprocessed:
            print(f"[FEEDBACKS] No unprocessed documents found.")
        else:
            stats = process_feedbacks(unprocessed, db, dry_run=args.dry_run)
            for k in total_stats:
                total_stats[k] += stats[k]

    if args.dry_run:
        print(f"\n[DRY RUN] Would process {total_stats['processed']} documents total.")
    else:
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Total processed:   {total_stats['processed']}")
        print(f"  Clean (usable):    {total_stats['clean']}")
        print(f"  Filtered:          {total_stats['filtered']}")
        print(f"  Empty:             {total_stats['empty']}")
        print(f"  Zawgyi detected:   {total_stats['zawgyi']}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
