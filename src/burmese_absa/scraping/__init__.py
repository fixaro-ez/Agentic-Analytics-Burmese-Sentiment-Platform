"""
burmese_absa.scraping — Facebook + Foodpanda + Blog scraping pipeline.

This package was extracted from the original monolithic `scraping.py` to keep
each concern isolated:
  - `_config`    : global constants (MongoDB URI, reaction keys, FOODPANDA_*)
  - `_common`    : shared utility functions (timestamp parsers, text normalizers)
  - `storage`    : in-memory `session_data` + JSON export
  - `lifecycle`  : 30-day MongoDB-backed lifecycle, get_db, indexes
  - `facebook`   : async Facebook post scraping + reaction breakdown + migration
  - `foodpanda`  : sync Foodpanda review scraping + business blog scraping
  - `cli`        : argparse entry point, `python -m burmese_absa` runs it

All public symbols that were importable from the original `scraping.py` are
re-exported here for backward compatibility.
"""

from __future__ import annotations

# --- Configuration constants ---
from ._config import (
    CONTENTS_COLLECTION,
    DB_NAME,
    FACEBOOK_TIMEZONE,
    FACEBOOK_TIMEZONE_NAME,
    FEEDBACKS_COLLECTION,
    FOODPANDA_ACTION_TIMEOUT_MS,
    FOODPANDA_GENERIC_AUTHORS,
    FOODPANDA_MAX_STEPS,
    FOODPANDA_MORE_LABEL_RE,
    FOODPANDA_NAVIGATION_TIMEOUT_MS,
    FOODPANDA_OVERALL_RATING,
    FOODPANDA_RESPONSE_HINTS,
    FOODPANDA_REVIEW_CARDS,
    FOODPANDA_REVIEW_LABEL_RE,
    FOODPANDA_REVIEW_MODAL,
    FOODPANDA_SCROLL_WAIT_MS,
    FOODPANDA_STALE_LIMIT,
    FOODPANDA_UI_CHROME_RE,
    LIFECYCLE_DAYS,
    MAX_ENGAGEMENT_HISTORY,
    MONGO_URI,
    REACTION_DIALOG_ATTEMPTS,
    REACTION_DIALOG_TIMEOUT_SECONDS,
    REACTION_KEYS,
)

# --- Shared utilities ---
from ._common import (
    make_scoped_id,
    normalize_foodpanda_rating,
    normalize_foodpanda_text,
    normalize_source_url,
    normalize_ui_text,
    parse_count,
    parse_foodpanda_relative_time,
    parse_relative_time,
    parse_scraped_datetime,
)

# --- In-memory storage ---
from .storage import (
    add_feedback,
    export_to_json,
    get_or_create_content,
    session_data,
)

# --- Lifecycle / MongoDB ---
from .lifecycle import (
    ensure_mongo_indexes,
    get_db,
    save_content_obj_to_mongo,
    save_session_data_to_mongo,
    show_tracking_status_db,
)

# --- Facebook scraping + migration ---
from .facebook import (
    ReactionScrapeResult,
    TimestampScrapeResult,
    _aggregate_metric,
    _canonical_post_permalink,
    _clean_facebook_post_text,
    _close_reaction_overlay,
    _count_info,
    _datetime_value,
    _discover_post_permalinks,  # noqa: F401  (re-exported for tests/back-compat)
    _empty_reactions,
    _extract_post_text,
    _extract_timestamp,
    _facebook_json_default,
    _facebook_page_slug,
    _fb_normalize_text,
    _find_reaction_summary,
    _href_belongs_to_facebook_page,
    _is_post_permalink,
    _legacy_breakdown,
    _looks_like_absolute_facebook_timestamp,
    _migration_metrics,
    _null_grouped_reactions,
    _normalize_url,
    _parse_reaction_payload,
    _parse_timestamp_text,
    _permalink_score,
    _persist_facebook_documents,
    _platform_content_id,
    _post_candidate_belongs_to_page,
    _reaction_root_payload,
    _reaction_toolbar,
    _reaction_type,
    _recover_post_surface_from_feed,  # noqa: F401
    _resolved_entity_name,
    _scoped_post_id,
    _summary_total,
    _validate_facebook_cookies,
    _wait_for_reaction_dialog,  # noqa: F401
    _write_facebook_json,
    _zero_reactions,
    compute_reaction_metrics,
    extract_reaction_breakdown,  # noqa: F401
    migrate_facebook_schema,
    run_facebook_page_scrape,
    scrape_facebook_post,  # noqa: F401
)

# --- Foodpanda scraping ---
from .foodpanda import (
    _foodpanda_review_card_count,
    _foodpanda_scroll_reviews_modal,
    _foodpanda_wait_for_more_reviews,
    canonical_foodpanda_shop_url,
    collect_foodpanda_review_response,
    derive_foodpanda_entity_name,
    dismiss_foodpanda_overlays,
    exhaust_foodpanda_reviews,
    extract_foodpanda_overall_rating,
    find_foodpanda_review_objects,
    foodpanda_dom_signature,
    foodpanda_review_id,
    foodpanda_review_modal_locator,
    foodpanda_reviews_url,
    foodpanda_vendor_code,
    harvest_foodpanda_records,
    is_foodpanda_modal_open,
    is_real_foodpanda_review,
    mounted_foodpanda_reviews,
    normalize_foodpanda_record,
    open_foodpanda_review_surface,
    scrape_business_blog,
    scrape_foodpanda_reviews,
    scrape_foodpanda_reviews_api,
    wait_for_foodpanda_review_modal,
)

# Back-compat: many names in the original scraping.py started with `_` but
# were used as the de-facto public API. We re-export them explicitly above.
# Any internal symbol that was previously importable from `scraping` should
# be listed here.

__all__ = [
    # config
    "CONTENTS_COLLECTION",
    "DB_NAME",
    "FACEBOOK_TIMEZONE",
    "FACEBOOK_TIMEZONE_NAME",
    "FEEDBACKS_COLLECTION",
    "FOODPANDA_ACTION_TIMEOUT_MS",
    "FOODPANDA_GENERIC_AUTHORS",
    "FOODPANDA_MAX_STEPS",
    "FOODPANDA_MORE_LABEL_RE",
    "FOODPANDA_NAVIGATION_TIMEOUT_MS",
    "FOODPANDA_OVERALL_RATING",
    "FOODPANDA_RESPONSE_HINTS",
    "FOODPANDA_REVIEW_CARDS",
    "FOODPANDA_REVIEW_LABEL_RE",
    "FOODPANDA_REVIEW_MODAL",
    "FOODPANDA_SCROLL_WAIT_MS",
    "FOODPANDA_STALE_LIMIT",
    "FOODPANDA_UI_CHROME_RE",
    "LIFECYCLE_DAYS",
    "MAX_ENGAGEMENT_HISTORY",
    "MONGO_URI",
    "REACTION_DIALOG_ATTEMPTS",
    "REACTION_DIALOG_TIMEOUT_SECONDS",
    "REACTION_KEYS",
    # common
    "make_scoped_id",
    "normalize_foodpanda_rating",
    "normalize_foodpanda_text",
    "normalize_source_url",
    "normalize_ui_text",
    "parse_count",
    "parse_foodpanda_relative_time",
    "parse_relative_time",
    "parse_scraped_datetime",
    # storage
    "add_feedback",
    "export_to_json",
    "get_or_create_content",
    "session_data",
    # lifecycle
    "ensure_mongo_indexes",
    "get_db",
    "save_content_obj_to_mongo",
    "save_session_data_to_mongo",
    "show_tracking_status_db",
    # facebook
    "ReactionScrapeResult",
    "TimestampScrapeResult",
    "_aggregate_metric",
    "_canonical_post_permalink",
    "_clean_facebook_post_text",
    "_close_reaction_overlay",
    "_count_info",
    "_datetime_value",
    "_empty_reactions",
    "_extract_post_text",
    "_extract_timestamp",
    "_facebook_json_default",
    "_facebook_page_slug",
    "_fb_normalize_text",
    "_find_reaction_summary",
    "_href_belongs_to_facebook_page",
    "_is_post_permalink",
    "_legacy_breakdown",
    "_looks_like_absolute_facebook_timestamp",
    "_migration_metrics",
    "_null_grouped_reactions",
    "_normalize_url",
    "_parse_reaction_payload",
    "_parse_timestamp_text",
    "_permalink_score",
    "_persist_facebook_documents",
    "_platform_content_id",
    "_post_candidate_belongs_to_page",
    "_reaction_root_payload",
    "_reaction_toolbar",
    "_reaction_type",
    "_resolved_entity_name",
    "_scoped_post_id",
    "_summary_total",
    "_validate_facebook_cookies",
    "_write_facebook_json",
    "_zero_reactions",
    "compute_reaction_metrics",
    "migrate_facebook_schema",
    "run_facebook_page_scrape",
    # foodpanda
    "_foodpanda_review_card_count",
    "_foodpanda_scroll_reviews_modal",
    "_foodpanda_wait_for_more_reviews",
    "canonical_foodpanda_shop_url",
    "collect_foodpanda_review_response",
    "derive_foodpanda_entity_name",
    "dismiss_foodpanda_overlays",
    "exhaust_foodpanda_reviews",
    "extract_foodpanda_overall_rating",
    "find_foodpanda_review_objects",
    "foodpanda_dom_signature",
    "foodpanda_review_id",
    "foodpanda_review_modal_locator",
    "foodpanda_reviews_url",
    "foodpanda_vendor_code",
    "harvest_foodpanda_records",
    "is_foodpanda_modal_open",
    "is_real_foodpanda_review",
    "mounted_foodpanda_reviews",
    "normalize_foodpanda_record",
    "open_foodpanda_review_surface",
    "scrape_business_blog",
    "scrape_foodpanda_reviews",
    "scrape_foodpanda_reviews_api",
    "wait_for_foodpanda_review_modal",
]
