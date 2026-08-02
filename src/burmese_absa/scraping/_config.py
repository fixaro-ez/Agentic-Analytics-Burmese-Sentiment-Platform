"""
Global configuration constants for the scraping package.

These were originally embedded at the top of `scraping.py`. They are grouped here
so every submodule can import them without circular dependencies.
"""

from __future__ import annotations

import re
from datetime import timedelta, timezone

from ..mongo_config import MONGO_URI

# ==========================================
# 30-Day Lifecycle Tracking Configuration (MongoDB-backed)
# ==========================================
LIFECYCLE_DAYS = 30  # Posts are tracked for this many days before finalization

# MongoDB Configuration — source of truth for dedup/lifecycle state
# (replaces the old tracking_state.json file)
DB_NAME = "feedback_analytics"
CONTENTS_COLLECTION = "contents"
FEEDBACKS_COLLECTION = "feedbacks"

# ==========================================
# Facebook Reaction Scraping Configuration
# ==========================================
REACTION_KEYS = ("like", "love", "care", "haha", "wow", "sad", "angry")
REACTION_DIALOG_TIMEOUT_SECONDS = 7.0
REACTION_DIALOG_ATTEMPTS = 2
MAX_ENGAGEMENT_HISTORY = 100
FACEBOOK_TIMEZONE_NAME = "Asia/Yangon"
FACEBOOK_TIMEZONE = timezone(timedelta(hours=6, minutes=30), name="MMT")

_BURMESE_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
_REACTION_ALIASES = {
    "like": ("like", "likes", "ကြိုက်တယ်", "သဘောကျ"),
    "love": ("love", "loves", "ချစ်တယ်", "ချစ်"),
    "care": ("care", "cares", "ဂရုစိုက်"),
    "haha": ("haha", "ဟားဟား"),
    "wow": ("wow", "ဝိုး", "အံ့ဩ"),
    "sad": ("sad", "ဝမ်းနည်း"),
    "angry": ("angry", "ဒေါသထွက်", "စိတ်ဆိုး"),
}
_POST_PATH_RE = re.compile(
    r"/(?:posts|photos?|videos?|reel|watch)/|/(?:permalink|story)\.php",
    re.IGNORECASE,
)
_COMPACT_COUNT_RE = re.compile(
    r"(?<![\w.])([0-9]+(?:[.,][0-9]+)*)\s*([KMB])?(?!\w)", re.IGNORECASE
)

# ==========================================
# Foodpanda Review Scraping Configuration
# ==========================================
FOODPANDA_NAVIGATION_TIMEOUT_MS = 60000
FOODPANDA_ACTION_TIMEOUT_MS = 4000
FOODPANDA_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
FOODPANDA_BROWSER_LOCALE = "en-US"
FOODPANDA_BROWSER_TIMEZONE = "Asia/Yangon"
FOODPANDA_REVIEWS_API_BASE = "https://reviews-api-mm.fd-api.com"
FOODPANDA_GLOBAL_ENTITY_ID = "FP_MM"
FOODPANDA_API_PAGE_SIZE = 50
FOODPANDA_API_MAX_REVIEWS = 500
FOODPANDA_MAX_STEPS = 120
FOODPANDA_STALE_LIMIT = 5
FOODPANDA_SCROLL_WAIT_MS = 2500
FOODPANDA_RESPONSE_HINTS = ('review', 'rating', 'graphql')
FOODPANDA_REVIEW_LABEL_RE = re.compile(
    r'reviews?|ratings?|customer feedback|သုံးသပ်ချက်|အဆင့်သတ်မှတ်', re.IGNORECASE)
FOODPANDA_MORE_LABEL_RE = re.compile(
    r'load more|show more|more reviews?|see more|နောက်ထပ်', re.IGNORECASE)
FOODPANDA_REVIEW_MODAL = (
    "[data-testid='info-reviews-modal-content'], #info-reviews-content"
)
FOODPANDA_REVIEW_CARDS = (
    "[data-testid='info-reviews-modal-card-container'], "
    "[data-testid='info-reviews-modal-review-card']"
)
FOODPANDA_OVERALL_RATING = "[data-testid='summary-section-rating-score']"
FOODPANDA_UI_CHROME_RE = re.compile(
    r'^(?:reviews?|ratings?|top reviews?|newest|highest rating|lowest rating|'
    r'helpful(?:\s+\d+)?|all ratings(?:\s*\([^)]*\))?|customer feedback|'
    r'\d+(?:\.\d+)?(?:\s*(?:out of|/)\s*\d+)?(?:\s*stars?)?|\d+\+?)$',
    re.IGNORECASE)
FOODPANDA_GENERIC_AUTHORS = frozenset({'unknown', 'customer', 'user', 'anonymous'})
