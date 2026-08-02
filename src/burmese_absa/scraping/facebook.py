"""
Facebook post scraping (Playwright async) and MongoDB persistence.

This module is the async Facebook pipeline. It writes directly to MongoDB
(no `session_data` involvement) and tracks a 30-day lifecycle.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse, urlunparse

from playwright.async_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from pymongo import UpdateOne

from ._common import normalize_ui_text, parse_relative_time
from ._config import (
    CONTENTS_COLLECTION,
    DB_NAME,
    FACEBOOK_TIMEZONE,
    FACEBOOK_TIMEZONE_NAME,
    LIFECYCLE_DAYS,
    MAX_ENGAGEMENT_HISTORY,
    REACTION_DIALOG_ATTEMPTS,
    REACTION_DIALOG_TIMEOUT_SECONDS,
    REACTION_KEYS,
    _BURMESE_DIGITS,
    _COMPACT_COUNT_RE,
    _POST_PATH_RE,
    _REACTION_ALIASES,
)

@dataclass
class ReactionScrapeResult:
    raw_reactions: dict[str, int | None]
    complete: bool
    exact: bool
    diagnostics: dict[str, Any]


@dataclass
class TimestampScrapeResult:
    value: datetime | None
    exact: bool
    source: str
    observed_label: str


def compute_reaction_metrics(
    raw_reactions: Mapping[str, int | None],
) -> dict[str, int | float | None]:
    """Calculate grouped Facebook reaction counts and sentiment ratios."""
    normalized: dict[str, int | None] = {}

    for key in REACTION_KEYS:
        value = raw_reactions.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"Reaction count {key!r} must be a non-negative integer or None"
                )
        normalized[key] = value

    supplied_total = raw_reactions.get("total")
    if supplied_total is not None:
        if (
            isinstance(supplied_total, bool)
            or not isinstance(supplied_total, int)
            or supplied_total < 0
        ):
            raise ValueError("Reaction total must be a non-negative integer or None")
        total: int | None = supplied_total
    elif all(value is not None for value in normalized.values()):
        total = sum(value for value in normalized.values() if value is not None)
    else:
        total = None

    if all(value is not None for value in normalized.values()):
        calculated_total = sum(
            value for value in normalized.values() if value is not None
        )
        if total is not None and total != calculated_total:
            raise ValueError(
                f"Reaction total mismatch: supplied={total}, calculated={calculated_total}"
            )

    def grouped_sum(*keys: str) -> int | None:
        values = [normalized[key] for key in keys]
        if any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    passive_engagement = grouped_sum("like")
    positive_affinity = grouped_sum("love", "care")
    negative_risk = grouped_sum("angry", "sad")
    expressive_virality = grouped_sum("haha", "wow")

    def safe_ratio(numerator: int | None) -> float | None:
        if numerator is None or total is None:
            return None
        if total == 0:
            return 0.0
        if numerator > total:
            raise ValueError(
                f"Grouped reaction count {numerator} exceeds total {total}"
            )
        return round(numerator / total, 6)

    return {
        "passive_engagement": passive_engagement,
        "positive_affinity": positive_affinity,
        "negative_risk": negative_risk,
        "expressive_virality": expressive_virality,
        "positivity_ratio": safe_ratio(positive_affinity),
        "negativity_ratio": safe_ratio(negative_risk),
        "haha_ratio": safe_ratio(normalized["haha"]),
    }


def _empty_reactions(total: int | None = None) -> dict[str, int | None]:
    return {**{key: None for key in REACTION_KEYS}, "total": total}


def _zero_reactions() -> dict[str, int]:
    return {**{key: 0 for key in REACTION_KEYS}, "total": 0}


def _null_grouped_reactions() -> dict[str, None]:
    return {
        "passive_engagement": None,
        "positive_affinity": None,
        "negative_risk": None,
        "expressive_virality": None,
        "positivity_ratio": None,
        "negativity_ratio": None,
        "haha_ratio": None,
    }


def _fb_normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_facebook_post_text(value: Any) -> str:
    text = _fb_normalize_text(value)
    return re.sub(r"\s+(?:See more|See less)$", "", text, flags=re.IGNORECASE).strip()


def _normalize_url(value: str) -> str:
    raw = _fb_normalize_text(value)
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/")
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(parsed._replace(path=path, query="", fragment=""))


def _scoped_post_id(page_url: str, identity: str) -> str:
    canonical = f"{_normalize_url(page_url)}\x1f{identity}"
    return "fb_post_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _content_hash(post_text: str, post_timestamp) -> str:
    """Compute a stable hash from post content for dedup when Facebook
    generates different pfbid values for the same post."""
    ts = post_timestamp.isoformat() if post_timestamp else ""
    canonical = f"{_fb_normalize_text(post_text)}\x1f{ts}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _platform_content_id(permalink: str) -> str:
    parsed = urlparse(unquote(permalink or ""))
    query = parse_qs(parsed.query)
    for key in ("story_fbid", "fbid", "v"):
        value = query.get(key, [""])[0]
        if value:
            return value
    segments = [part for part in parsed.path.split("/") if part]
    for marker in ("posts", "videos", "reel"):
        if marker in segments:
            index = segments.index(marker)
            if index + 1 < len(segments):
                return segments[index + 1]
    for segment in reversed(segments):
        if segment.startswith("pfbid") or segment.isdigit():
            return segment
    return ""


def _is_post_permalink(href: str) -> bool:
    if not href:
        return False
    parsed = urlparse(href)
    looks_like_post = bool(_POST_PATH_RE.search(parsed.path)) or any(
        key in parse_qs(parsed.query) for key in ("story_fbid", "fbid", "v")
    )
    return looks_like_post and bool(_platform_content_id(href))


def _permalink_score(href: str) -> int:
    lowered = href.casefold()
    score = 0
    if "/posts/" in lowered:
        score += 100
    elif "permalink.php" in lowered or "story_fbid=" in lowered:
        score += 90
    elif "/videos/" in lowered or "/reel/" in lowered:
        score += 80
    elif "/photo" in lowered or "fbid=" in lowered:
        score += 60
    if "comment_id=" in lowered or "reply_comment_id=" in lowered:
        score -= 10
    return score


def _canonical_post_permalink(href: str, page_url: str) -> str:
    absolute = urljoin(page_url, href).split("#", 1)[0]
    parsed = urlparse(absolute)
    query = parse_qs(parsed.query)
    if parsed.path.casefold().endswith(("/permalink.php", "/story.php")):
        keep = {
            key: values[0]
            for key, values in query.items()
            if key in {"story_fbid", "id"} and values
        }
    elif "/photo" in parsed.path.casefold():
        keep = {"fbid": query["fbid"][0]} if query.get("fbid") else {}
    elif "/watch" in parsed.path.casefold():
        keep = {"v": query["v"][0]} if query.get("v") else {}
    else:
        keep = {}
    return urlunparse(parsed._replace(query=urlencode(keep), fragment=""))


def _facebook_page_slug(page_url: str) -> str:
    """Return the stable page/profile path segment used to reject foreign posts."""
    segments = [part for part in urlparse(page_url).path.split("/") if part]
    if not segments:
        return ""
    first = segments[0].casefold()
    if first in {"pages", "profile.php", "permalink.php", "story.php"}:
        return ""
    return first


def _href_belongs_to_facebook_page(href: str, page_url: str) -> bool:
    """Check page ownership by URL path, ignoring Facebook tracking parameters."""
    expected = _facebook_page_slug(page_url)
    if not expected:
        return True
    absolute = urljoin(page_url, href)
    segments = [part for part in urlparse(absolute).path.split("/") if part]
    return bool(segments) and segments[0].casefold() == expected


def _post_candidate_belongs_to_page(href: str, page_url: str) -> bool:
    """Validate a post candidate after its containing post author was verified."""
    parsed = urlparse(urljoin(page_url, href))
    segments = [part.casefold() for part in parsed.path.split("/") if part]
    # Facebook reel URLs are global (/reel/<id>) and do not include the page
    # slug. Ownership comes from the already-validated surrounding post card.
    if segments and segments[0] in {"reel", "watch"}:
        return True
    return _href_belongs_to_facebook_page(href, page_url)


def _count_info(raw: Any) -> tuple[int | None, bool]:
    """Return (numeric value, exact). Compact K/M/B values are approximate."""
    text = _fb_normalize_text(raw).translate(_BURMESE_DIGITS)
    matches = list(_COMPACT_COUNT_RE.finditer(text.replace("\u00a0", " ")))
    if not matches:
        return None, False
    match = matches[-1]
    number_text = match.group(1)
    suffix = (match.group(2) or "").upper()
    if suffix:
        number = float(number_text.replace(",", "."))
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
        return int(round(number * multiplier)), False
    return int(number_text.replace(",", "")), True


def _reaction_type(label: str) -> str | None:
    normalized = _fb_normalize_text(label).casefold()
    for reaction, aliases in _REACTION_ALIASES.items():
        for alias in aliases:
            folded = alias.casefold()
            if folded.isascii():
                if re.search(rf"(?<![a-z]){re.escape(folded)}(?![a-z])", normalized):
                    return reaction
            elif folded in normalized:
                return reaction
    return None


def _validate_facebook_cookies(cookie_path: str) -> tuple[int, int, list[str]]:
    """Validate Facebook cookies before scraping.
    
    Returns:
        tuple: (total_cookies, valid_cookies, list_of_warnings)
    """
    warnings = []
    
    if not os.path.exists(cookie_path):
        return 0, 0, [f"Cookie file not found: {cookie_path}"]
    
    if os.path.getsize(cookie_path) == 0:
        return 0, 0, [f"Cookie file is empty: {cookie_path}"]
    
    try:
        with open(cookie_path, "r", encoding="utf-8") as handle:
            raw_cookies = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return 0, 0, [f"Cannot parse cookie file: {exc}"]
    
    if not isinstance(raw_cookies, list):
        return 0, 0, ["Cookie JSON must be a list"]
    
    total = len(raw_cookies)
    valid = 0
    now = time.time()
    expired_count = 0
    missing_fields = 0
    
    for cookie in raw_cookies:
        if not all(cookie.get(key) for key in ("name", "value", "domain", "path")):
            missing_fields += 1
            continue
        
        expires = cookie.get("expirationDate")
        if expires is not None:
            try:
                if float(expires) < now:
                    expired_count += 1
                    continue
            except (ValueError, TypeError):
                pass
        
        valid += 1
    
    if expired_count > 0:
        warnings.append(f"{expired_count}/{total} cookies are expired")
    
    if missing_fields > 0:
        warnings.append(f"{missing_fields}/{total} cookies missing required fields")
    
    critical_cookies = {"c_user", "xs", "fr", "datr"}
    found_names = {c.get("name") for c in raw_cookies if isinstance(c, dict)}
    missing_critical = critical_cookies - found_names
    if missing_critical:
        warnings.append(f"Missing critical cookies: {', '.join(sorted(missing_critical))}")
    
    return total, valid, warnings


async def _load_cookies(context, cookie_path: str) -> int:
    if not os.path.exists(cookie_path) or os.path.getsize(cookie_path) == 0:
        print(f"[WARN] Facebook cookie file is missing or empty: {cookie_path}")
        return 0
    try:
        with open(cookie_path, "r", encoding="utf-8") as handle:
            raw_cookies = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Cannot load Facebook cookies: {exc}")
        return 0
    if not isinstance(raw_cookies, list):
        print("[WARN] Facebook cookie JSON must be a list.")
        return 0

    converted = []
    for cookie in raw_cookies:
        if not all(cookie.get(key) for key in ("name", "value", "domain", "path")):
            continue
        item = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie["domain"],
            "path": cookie["path"],
            "secure": bool(cookie.get("secure", False)),
            "httpOnly": bool(cookie.get("httpOnly", False)),
        }
        if cookie.get("expirationDate") is not None:
            item["expires"] = float(cookie["expirationDate"])
        same_site = str(cookie.get("sameSite", "Lax")).casefold()
        item["sameSite"] = {
            "no_restriction": "None",
            "unspecified": "Lax",
        }.get(same_site, same_site.capitalize())
        converted.append(item)
    if converted:
        await context.add_cookies(converted)
    return len(converted)


async def _goto_recoverable(page: Page, url: str) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PlaywrightTimeoutError:
        if await page.locator("body").count() == 0:
            raise
        print(f"[WARN] Navigation timed out but DOM is available: {url}")


async def _dismiss_facebook_overlays(page: Page) -> None:
    patterns = re.compile(
        r"^(?:Allow all cookies|Only allow essential cookies|Not now|Close|ပိတ်)$",
        re.IGNORECASE,
    )
    for role in ("button", "link"):
        candidates = page.get_by_role(role, name=patterns)
        for index in range(min(await candidates.count(), 5)):
            candidate = candidates.nth(index)
            try:
                if await candidate.is_visible():
                    await candidate.click(timeout=1_500)
                    break
            except Exception:
                continue


async def _detect_interruption(page: Page) -> str | None:
    url = page.url.casefold()
    if any(token in url for token in ("/login", "/checkpoint", "/recover")):
        return "login_or_checkpoint"
    try:
        body = (await page.locator("body").inner_text(timeout=2_000)).casefold()[:15_000]
    except Exception:
        return None
    patterns = {
        "login_required": ("log in to facebook", "you must log in"),
        "rate_limited": ("try again later", "temporarily blocked", "going too fast"),
        "unavailable": ("this content isn't available", "content is not available"),
    }
    for reason, phrases in patterns.items():
        if any(phrase in body for phrase in phrases):
            return reason
    return None


def _reaction_count_info(label: str, reaction: str) -> tuple[int | None, bool]:
    """Parse only a count attached to the requested reaction label."""
    text = _fb_normalize_text(label).translate(_BURMESE_DIGITS)
    count_pattern = r"([0-9]+(?:[.,][0-9]+)*\s*[KMB]?)"
    matches: list[tuple[int, bool]] = []
    for alias in _REACTION_ALIASES.get(reaction, ()):
        escaped = re.escape(alias)
        if alias.isascii():
            alias_pattern = rf"(?<![a-z]){escaped}(?![a-z])"
        else:
            alias_pattern = escaped
        patterns = (
            re.compile(
                rf"{alias_pattern}\s*[:\u00b7]?\s*{count_pattern}",
                re.IGNORECASE,
            ),
            re.compile(
                rf"{count_pattern}\s*(?:people\s+)?{alias_pattern}",
                re.IGNORECASE,
            ),
        )
        for pattern in patterns:
            for match in pattern.finditer(text):
                value, exact = _count_info(match.group(1))
                if value is not None:
                    matches.append((value, exact))
    return max(matches, key=lambda item: item[0], default=(None, False))


def _facebook_interruption_message(reason: str, requested_url: str) -> str:
    if reason in {"login_or_checkpoint", "login_required"}:
        return (
            "Facebook requires sign-in or checkpoint confirmation. Refresh "
            "cookies.json after completing the checkpoint in a normal browser."
        )
    if reason == "rate_limited":
        return (
            "Facebook temporarily rate-limited this session. Wait before retrying "
            "and avoid starting overlapping Facebook scrapes."
        )
    if reason == "unavailable":
        return (
            f"Facebook says the page is unavailable: {requested_url}. Verify the "
            "exact page address. Facebook usernames do not contain spaces; for "
            "Lotteria Myanmar use https://www.facebook.com/LotteriaMyanmar."
        )
    return f"Facebook interrupted the scrape while opening {requested_url}."


async def _is_authenticated(page: Page) -> bool:
    login_controls = page.locator(
        "input[name='email'], input[name='pass'], form[action*='login']"
    )
    if await login_controls.count():
        return False
    return True


async def _discover_post_permalinks(
    page: Page, page_url: str, max_posts: int
) -> list[str]:
    if _is_post_permalink(page_url):
        return [page_url]

    posts_by_position: dict[int, str] = {}
    seen: set[str] = set()
    normalized_page_url = _normalize_url(page_url).rstrip("/")
    discovery_urls = [
        f"{normalized_page_url}/posts",
        f"{normalized_page_url}?sk=posts",
        normalized_page_url,
    ]
    unavailable_routes = 0

    for navigation_attempt, discovery_url in enumerate(discovery_urls, 1):
        await _goto_recoverable(page, discovery_url)
        await _dismiss_facebook_overlays(page)
        interruption = await _detect_interruption(page)
        if interruption:
            if interruption == "unavailable":
                unavailable_routes += 1
                print(
                    f"[WARN] Facebook marked discovery route unavailable: "
                    f"{discovery_url}"
                )
                continue
            raise RuntimeError(
                _facebook_interruption_message(interruption, page_url)
            )
        positioned_posts = page.locator("div[aria-posinset]")
        fallback_articles = page.locator("div[role='article'], article")
        try:
            await page.wait_for_function(
                r"""() => Array.from(document.querySelectorAll('a[href]')).some(a => {
                    const href = a.href || a.getAttribute('href') || '';
                    return /\/(posts|videos|reel)\//i.test(href)
                        || /(?:story_fbid|fbid)=/i.test(href);
                })""",
                timeout=15_000,
            )
        except PlaywrightTimeoutError:
            pass

        stale_rounds = 0
        max_scroll_attempts = 30  # More aggressive scrolling
        for scroll_attempt in range(max_scroll_attempts):
            before_scan = len(posts_by_position)
            positioned_count = await positioned_posts.count()
            if positioned_count:
                containers: list[Locator] = [
                    positioned_posts.nth(index)
                    for index in range(min(positioned_count, max(max_posts * 4, 20)))
                ]
            else:
                article_count = await fallback_articles.count()
                containers = [
                    fallback_articles.nth(index)
                    for index in range(min(article_count, 100))
                ]
            if not containers:
                containers = [page.locator("body")]

            for post in containers:
                try:
                    position = await post.get_attribute("aria-posinset")
                    container_payload = await post.evaluate(
                        """node => ({
                            text: (node.innerText || '').slice(0, 12000),
                            actions: Array.from(node.querySelectorAll('[aria-label]'))
                                .slice(0, 250)
                                .map(item => item.getAttribute('aria-label') || ''),
                            hrefs: Array.from(node.querySelectorAll('a[href]'))
                                .slice(0, 350)
                                .map(item => item.href || item.getAttribute('href') || '')
                        })"""
                    )
                    container_text = _fb_normalize_text(
                        container_payload.get("text")
                    ).casefold()
                    action_labels = " ".join(
                        container_payload.get("actions") or []
                    ).casefold()
                    if not position and not (
                        "actions for this post by" in action_labels
                        and ("comment" in action_labels or "share" in action_labels)
                    ):
                        continue
                    hrefs = container_payload.get("hrefs") or []
                except Exception:
                    continue
                # A Facebook page feed can inject recommendations and unrelated
                # posts. Require both an author/profile link and a post URL owned
                # by the requested page before accepting a container.
                owns_container = any(
                    _href_belongs_to_facebook_page(href, page_url) for href in hrefs
                )
                if not owns_container:
                    continue
                candidates = [
                    href
                    for href in hrefs
                    if _is_post_permalink(href)
                    and _post_candidate_belongs_to_page(href, page_url)
                ]
                if not candidates:
                    continue
                permalink = _canonical_post_permalink(
                    max(candidates, key=_permalink_score), page_url
                )
                key = _platform_content_id(permalink) or permalink
                if key not in seen:
                    seen.add(key)
                    try:
                        feed_position = int(position or "")
                    except ValueError:
                        feed_position = 1_000_000 + len(posts_by_position)
                    while feed_position in posts_by_position:
                        feed_position += 1
                    posts_by_position[feed_position] = permalink
                    print(f"[DEBUG] Found post at position {feed_position}: {permalink[:60]}...")

            try:
                global_hrefs = await page.locator("a[href]").evaluate_all(
                    "nodes => nodes.slice(0, 1000).map(node => node.href || node.getAttribute('href') || '')"
                )
            except Exception:
                global_hrefs = []
            # Facebook frequently exposes permalink anchors outside the
            # aria-posinset wrapper (especially on /posts and virtualized feeds).
            # Process these on every round, not only when no positioned wrapper
            # exists.
            for href in global_hrefs:
                if not (
                    _is_post_permalink(href)
                    and _permalink_score(href) >= 80
                    and _href_belongs_to_facebook_page(href, page_url)
                    and _post_candidate_belongs_to_page(href, page_url)
                ):
                    continue
                permalink = _canonical_post_permalink(href, page_url)
                key = _platform_content_id(permalink) or permalink
                if key in seen:
                    continue
                seen.add(key)
                fallback_position = 1_000_000 + len(posts_by_position)
                posts_by_position[fallback_position] = permalink
                print(
                    f"[DEBUG] Found fallback post at position "
                    f"{fallback_position}: {permalink[:60]}..."
                )

            discovered_this_round = len(posts_by_position) - before_scan
            stale_rounds = 0 if discovered_this_round else stale_rounds + 1

            if len(posts_by_position) >= max_posts:
                print(
                    f"[INFO] Discovered {len(posts_by_position)} unique posts; "
                    f"requested {max_posts}."
                )
                break

            # Scroll both the last mounted post and the document. Facebook uses
            # virtualized/nested feed containers, so relying on mouse.wheel alone
            # can leave the feed pinned to its first card.
            if containers:
                try:
                    await containers[-1].scroll_into_view_if_needed(timeout=2_000)
                except Exception:
                    pass
            await page.evaluate(
                """() => {
                    const root = document.scrollingElement || document.documentElement;
                    root.scrollBy(0, Math.max(window.innerHeight * 1.5, 1600));
                }"""
            )
            await page.mouse.wheel(0, 2_500)
            # Wait for new content to load
            try:
                await page.wait_for_function(
                    "previous => document.querySelectorAll('a[href]').length > previous",
                    arg=len(global_hrefs),
                    timeout=3_000,
                )
            except PlaywrightTimeoutError:
                pass
            await asyncio.sleep(0.75)
            
            if stale_rounds >= 8:  # More tolerance for stale rounds
                print(f"[INFO] No new posts for 8 scroll attempts, collected {len(posts_by_position)} posts")
                break

        if len(posts_by_position) >= max_posts:
            break
        if posts_by_position:
            print(
                f"[WARN] Found only {len(posts_by_position)}/{max_posts} posts "
                f"via {discovery_url}; trying another Facebook feed route."
            )
        else:
            print(
                f"[WARN] No post permalink found after page-load attempt "
                f"{navigation_attempt}/{len(discovery_urls)}; retrying."
            )

    if not posts_by_position and unavailable_routes == len(discovery_urls):
        raise RuntimeError(_facebook_interruption_message("unavailable", page_url))

    return [
        posts_by_position[item]
        for item in sorted(posts_by_position)[:max_posts]
    ]


async def _post_surface_score(
    candidate: Locator, platform_id: str, page_identity: str = ""
) -> int:
    try:
        handle = await candidate.element_handle(timeout=700)
        if handle is None:
            return -1
        visible = await handle.is_visible()
        payload = await handle.evaluate(
            """node => ({
                role: node.getAttribute('role') || '',
                tag: node.tagName || '',
                text: (node.innerText || '').slice(0, 12000),
                hrefs: Array.from(node.querySelectorAll('a[href]')).slice(0, 100)
                    .map(a => a.href || a.getAttribute('href') || ''),
                messages: node.querySelectorAll(
                    '[data-ad-comet-preview="message"], [data-ad-preview="message"]'
                ).length,
                actions: Array.from(node.querySelectorAll('[role="button"]')).slice(0, 100)
                    .map(el => el.getAttribute('aria-label') || el.innerText || '')
            })"""
        )
    except Exception:
        return -1
    text = _fb_normalize_text(payload.get("text"))
    actions = " ".join(payload.get("actions") or []).casefold()
    normalized_actions = re.sub(r"[^a-z0-9]", "", actions)
    has_platform_id = bool(platform_id) and any(
        platform_id in href for href in payload.get("hrefs") or []
    )
    if platform_id and not has_platform_id:
        return -1
    identity_matches = bool(page_identity) and page_identity in normalized_actions
    # Facebook sometimes keeps the exact permalink post inside a hidden dialog
    # while a visual shell is mounted elsewhere. Accept a hidden candidate only
    # when both the post ID and page identity correlate; this avoids selecting
    # unrelated background/recommended posts.
    if not visible and not (has_platform_id and identity_matches):
        return -1
    score = 0
    if payload.get("role") == "dialog":
        score += 60
    elif payload.get("role") == "main" or payload.get("tag") == "MAIN":
        score += 25
    if has_platform_id:
        score += 50
    if identity_matches:
        score += 80
    if payload.get("messages"):
        score += 25
    if "like" in actions:
        score += 8
    if "share" in actions:
        score += 8
    if "reaction" in actions:
        score += 8
    if len(text) > 20:
        score += 3
    # A mounted feed/dialog can retain a hidden stale copy of the same post.
    # Always prefer the visible copy when both carry the exact permalink.
    score += 200 if visible else -10
    return score


async def _locate_post_surface(
    page: Page, permalink: str, timeout_seconds: float = 15.0
) -> Locator:
    platform_id = _platform_content_id(permalink)
    path = urlparse(permalink).path.casefold()
    path_segments = [segment for segment in path.split("/") if segment]
    page_identity = ""
    for marker_name in ("posts", "videos", "reel"):
        if marker_name in path_segments:
            marker_index = path_segments.index(marker_name)
            if marker_index > 0:
                page_identity = re.sub(
                    r"[^a-z0-9]", "", path_segments[marker_index - 1]
                )
            break
    requires_dialog = (
        "/posts/" in path
        or "/photo" in path
        or path.endswith("/permalink.php")
        or path.endswith("/story.php")
    )
    minimum_score = 80 if requires_dialog else 20
    candidates = page.locator(
        "div[role='dialog'], main div[role='article'], "
        "div[aria-posinset], article"
    )
    deadline = time.monotonic() + timeout_seconds
    marker = "data-codex-facebook-post-surface"
    token = hashlib.sha1(permalink.encode("utf-8")).hexdigest()
    while time.monotonic() < deadline:
        await page.locator(f'[{marker}="{token}"]').evaluate_all(
            "(nodes, name) => nodes.forEach(node => node.removeAttribute(name))",
            marker,
        )

        # Primary path: start at a link containing the exact post ID, then walk
        # upward to the smallest ancestor that owns the post action/engagement
        # controls. This prevents a broad <main> or a recommended post from being
        # correlated merely because it also contains the target link elsewhere.
        if platform_id:
            direct_match = await page.evaluate(
                """({platformId, marker, token}) => {
                    const visible = node => {
                        const rect = node.getBoundingClientRect();
                        const style = getComputedStyle(node);
                        return rect.width > 0 && rect.height > 0
                            && style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    const labels = node => Array.from(node.querySelectorAll('[aria-label]'))
                        .slice(0, 300)
                        .map(el => (el.getAttribute('aria-label') || '').toLowerCase());
                    const hasPostControls = node => {
                        const values = labels(node);
                        const hasAction = values.some(value =>
                            value.startsWith('actions for this post by'));
                        const hasEngagement = values.some(value =>
                            value.startsWith('all reactions:')
                            || /\bcomments?\b/.test(value)
                            || /\bshares?\b/.test(value)
                            || value.startsWith('comment on '));
                        return hasAction && hasEngagement;
                    };
                    const isConcretePostSurface = node =>
                        node.hasAttribute('aria-posinset')
                        || node.getAttribute('role') === 'dialog'
                        || node.getAttribute('role') === 'article'
                        || node.tagName === 'ARTICLE';
                    const anchors = Array.from(document.querySelectorAll('a[href]'))
                        .filter(anchor => (anchor.href || '').includes(platformId));
                    const matches = [];
                    for (const anchor of anchors) {
                        let node = anchor;
                        for (let depth = 0; node && depth < 18; depth += 1, node = node.parentElement) {
                            if (isConcretePostSurface(node)
                                    && visible(node) && hasPostControls(node)) {
                                matches.push({node, depth, size: (node.innerText || '').length});
                                break;
                            }
                        }
                    }
                    if (!matches.length) return null;
                    matches.sort((a, b) => a.depth - b.depth || a.size - b.size);
                    matches[0].node.setAttribute(marker, token);
                    return {depth: matches[0].depth, size: matches[0].size};
                }""",
                {"platformId": platform_id, "marker": marker, "token": token},
            )
            marked = page.locator(f'[{marker}="{token}"]')
            if direct_match and await marked.count() == 1:
                return marked

        best_score = -1
        best_is_acceptable = False
        best_candidate: Locator | None = None
        for index in range(min(await candidates.count(), 80)):
            candidate = candidates.nth(index)
            score = await _post_surface_score(candidate, platform_id, page_identity)
            if score > best_score:
                try:
                    candidate_role = await candidate.get_attribute("role", timeout=700)
                    best_score = score
                    best_candidate = candidate
                    candidate_threshold = (
                        minimum_score
                        if candidate_role == "dialog" or not requires_dialog
                        else 100
                    )
                    best_is_acceptable = score >= candidate_threshold
                except Exception:
                    continue
        if best_is_acceptable and best_candidate is not None:
            # Mark only the final winner. The old code marked every temporary
            # leader and returned the first marker, which mixed unrelated post
            # text with the target permalink and MongoDB identity.
            await page.locator(f'[{marker}="{token}"]').evaluate_all(
                "(nodes, name) => nodes.forEach(node => node.removeAttribute(name))",
                marker,
            )
            try:
                await best_candidate.evaluate(
                    "(node, payload) => node.setAttribute(payload.marker, payload.token)",
                    {"marker": marker, "token": token},
                )
            except Exception:
                await asyncio.sleep(0.2)
                continue
            marked = page.locator(f'[{marker}="{token}"]')
            if await marked.count() == 1:
                return marked
        await asyncio.sleep(0.2)
    try:
        debug_candidates = await page.evaluate(
            """platformId => Array.from(document.querySelectorAll(
                'div[role="dialog"], div[role="article"], div[aria-posinset], article'
            )).slice(0, 40).map(node => ({
                tag: node.tagName,
                role: node.getAttribute('role') || '',
                pos: node.getAttribute('aria-posinset') || '',
                visible: !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length),
                hasId: Array.from(node.querySelectorAll('a[href]'))
                    .some(anchor => (anchor.href || '').includes(platformId)),
                actions: Array.from(node.querySelectorAll('[aria-label]'))
                    .map(item => item.getAttribute('aria-label') || '')
                    .filter(label => /post by|all reactions|comments|shares/i.test(label))
                    .slice(0, 8)
            })).filter(item => item.hasId || item.actions.length)""",
            platform_id,
        )
    except Exception:
        debug_candidates = []
    raise RuntimeError(
        "No correlated Facebook post surface was found "
        f"(url={page.url!r}, platform_id={platform_id!r}, "
        f"candidates={debug_candidates[:8]!r})"
    )


async def _fb_label(locator: Locator) -> str:
    try:
        return _fb_normalize_text(
            " ".join(
                filter(
                    None,
                    (
                        await locator.get_attribute("aria-label", timeout=800),
                        await locator.get_attribute("title", timeout=800),
                        await locator.inner_text(timeout=800),
                    ),
                )
            )
        )
    except Exception:
        return ""


async def _recover_post_surface_from_feed(
    page: Page, page_url: str, permalink: str, max_scrolls: int = 10
) -> Locator | None:
    """Reload the page feed and scroll until the exact post ID is mounted."""
    await _goto_recoverable(page, page_url)
    await _dismiss_facebook_overlays(page)
    for attempt in range(max_scrolls + 1):
        try:
            return await _locate_post_surface(
                page, permalink, timeout_seconds=1.25
            )
        except RuntimeError:
            if attempt >= max_scrolls:
                break
        await page.mouse.wheel(0, 1_500)
        try:
            await page.wait_for_function(
                """platformId => Array.from(document.querySelectorAll('a[href]'))
                    .some(anchor => (anchor.href || '').includes(platformId))""",
                arg=_platform_content_id(permalink),
                timeout=1_500,
            )
        except PlaywrightTimeoutError:
            pass
    return None


async def _extract_post_text(surface: Locator) -> str:
    visible_messages = surface.locator(
        "div[data-ad-comet-preview='message']:visible, "
        "div[data-ad-preview='message']:visible"
    )
    messages = (
        visible_messages
        if await visible_messages.count()
        else surface.locator(
            "div[data-ad-comet-preview='message'], div[data-ad-preview='message']"
        )
    )
    if await messages.count():
        see_more = messages.first.get_by_text(
            re.compile(r"^(?:See more|ပိုမိုကြည့်ရှုရန်)$", re.IGNORECASE), exact=True
        )
        if await see_more.count():
            try:
                if await see_more.first.is_visible():
                    await see_more.first.click(timeout=1_500)
                    messages = surface.locator(
                        "div[data-ad-comet-preview='message']:visible, "
                        "div[data-ad-preview='message']:visible"
                    )
            except Exception:
                pass
        try:
            raw_text = await messages.first.inner_text(timeout=3_000)
        except Exception:
            raw_text = await messages.first.text_content(timeout=3_000) or ""
        return _clean_facebook_post_text(raw_text)
    try:
        surface_role = await surface.get_attribute("role")
        surface_tag = await surface.evaluate("node => node.tagName")
    except Exception:
        return ""
    if surface_role != "main" and surface_tag != "MAIN":
        return ""
    try:
        lines = [
            _fb_normalize_text(line)
            for line in (await surface.inner_text(timeout=2_000)).splitlines()
        ]
    except Exception:
        return ""
    excluded = re.compile(
        r"^(?:follow|like|react|comment|share|menu|previous|next|original audio|"
        r"shared with public|[\d.,]+[kmb]?)$",
        re.IGNORECASE,
    )
    candidates = [
        line
        for line in lines
        if len(line) >= 20
        and not excluded.fullmatch(line)
        and "original audio" not in line.casefold()
    ]
    return max(candidates, key=len, default="")


def _parse_timestamp_text(value: str, now: datetime) -> datetime | None:
    text = _fb_normalize_text(value)
    if not text:
        return None
    iso = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso)
        if parsed.tzinfo is None and now.tzinfo is not None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        return parsed
    except ValueError:
        pass
    lowered = text.casefold()

    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    us_absolute = re.search(
        r"\b(" + "|".join(months) + r")\s+(\d{1,2}),\s*(\d{4})\s+"
        r"at\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?\b",
        lowered,
    )
    if us_absolute:
        month_name, day, year, hour, minute, second, meridiem = (
            us_absolute.groups()
        )
        hour_value = int(hour)
        if meridiem == "pm" and hour_value != 12:
            hour_value += 12
        elif meridiem == "am" and hour_value == 12:
            hour_value = 0
        return datetime(
            int(year), months[month_name], int(day), hour_value,
            int(minute), int(second or 0), tzinfo=now.tzinfo,
        )

    dmy_absolute = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(months) + r")\s+(\d{4})\s+"
        r"at\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?\b",
        lowered,
    )
    if dmy_absolute:
        day, month_name, year, hour, minute, second, meridiem = (
            dmy_absolute.groups()
        )
        hour_value = int(hour)
        if meridiem == "pm" and hour_value != 12:
            hour_value += 12
        elif meridiem == "am" and hour_value == 12:
            hour_value = 0
        return datetime(
            int(year), months[month_name], int(day), hour_value,
            int(minute), int(second or 0), tzinfo=now.tzinfo,
        )

    if lowered in {"yesterday", "a day ago", "an day ago"}:
        return now - timedelta(days=1)
    match = re.search(
        r"\b(\d+|a|an)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|"
        r"d|day|days|w|week|weeks)(?:\s+ago)?\b",
        lowered,
    )
    if match:
        value_int = 1 if match.group(1) in {"a", "an"} else int(match.group(1))
        unit = match.group(2)[0]
        delta = {
            "m": timedelta(minutes=value_int),
            "h": timedelta(hours=value_int),
            "d": timedelta(days=value_int),
            "w": timedelta(weeks=value_int),
        }[unit]
        return now - delta
    return None


def _looks_like_absolute_facebook_timestamp(value: str) -> bool:
    lowered = _fb_normalize_text(value).casefold()
    return bool(
        re.search(r"\b20\d{2}\b", lowered)
        and re.search(
            r"\b(?:january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\b",
            lowered,
        )
    )


async def _extract_timestamp(
    surface: Locator, now: datetime
) -> TimestampScrapeResult:
    machine = surface.locator("time[datetime], abbr[data-utime], [data-utime]")
    for index in range(min(await machine.count(), 10)):
        item = machine.nth(index)
        epoch = await item.get_attribute("data-utime")
        if epoch and epoch.isdigit():
            return TimestampScrapeResult(
                datetime.fromtimestamp(int(epoch), tz=now.tzinfo),
                True,
                "machine_epoch",
                epoch,
            )
        datetime_label = await item.get_attribute("datetime") or ""
        parsed = _parse_timestamp_text(datetime_label, now)
        if parsed:
            return TimestampScrapeResult(
                parsed, True, "machine_datetime", datetime_label
            )

    relative_fallback: TimestampScrapeResult | None = None
    links = surface.locator("a[href]")
    for index in range(min(await links.count(), 80)):
        link = links.nth(index)
        href = await link.get_attribute("href") or ""
        # Comment and reply permalinks expose comment timestamps inside the same
        # post surface. They must never become the post timestamp.
        if "comment_id=" in href or "reply_comment_id=" in href:
            continue
        accessible_values = [
            await link.get_attribute("aria-label"),
            await link.get_attribute("title"),
        ]
        try:
            # Facebook deliberately scrambles timestamp characters in the DOM
            # and restores their order through CSS. The accessibility snapshot
            # retains the user-visible name (for example "2 days ago").
            aria_value = await link.aria_snapshot(timeout=800)
            # Parse only the role/name line. Snapshot URL lines contain opaque
            # tracking tokens that can accidentally resemble "2h" or "5m".
            accessible_values.append(aria_value.splitlines()[0] if aria_value else "")
        except Exception:
            pass
        descendants = link.locator("[aria-label], [title]")
        for descendant_index in range(min(await descendants.count(), 6)):
            descendant = descendants.nth(descendant_index)
            accessible_values.extend(
                [
                    await descendant.get_attribute("aria-label"),
                    await descendant.get_attribute("title"),
                ]
            )
        parsed_accessible: list[tuple[datetime, str]] = []
        for value in accessible_values:
            parsed = _parse_timestamp_text(value or "", now)
            if parsed:
                if _looks_like_absolute_facebook_timestamp(value or ""):
                    return TimestampScrapeResult(
                        parsed, True, "accessible_absolute", value or ""
                    )
                parsed_accessible.append((parsed, value or ""))

        href_lower = href.casefold()
        is_timestamp_link = bool(parsed_accessible) or (
            index < 8
            and "__tn__=%2co" in href_lower
            and "/photo" not in href_lower
        )
        if not is_timestamp_link:
            continue

        if parsed_accessible and relative_fallback is None:
            relative_fallback = TimestampScrapeResult(
                parsed_accessible[0][0],
                False,
                "accessible_relative",
                parsed_accessible[0][1],
            )
        try:
            await link.hover(timeout=1_500)
            visible_tooltips = link.page.locator("[role='tooltip']:visible")
            try:
                await visible_tooltips.last.wait_for(
                    state="visible", timeout=2_500
                )
            except PlaywrightTimeoutError:
                pass
            tooltips = link.page.get_by_role("tooltip")
            tooltip_count = await tooltips.count()
            for tooltip_index in reversed(range(tooltip_count)):
                tooltip = tooltips.nth(tooltip_index)
                if not await tooltip.is_visible():
                    continue
                tooltip_values = [await tooltip.inner_text(timeout=1_500)]
                try:
                    tooltip_values.append(await tooltip.aria_snapshot(timeout=1_500))
                except Exception:
                    pass
                for tooltip_value in tooltip_values:
                    if not _looks_like_absolute_facebook_timestamp(tooltip_value):
                        continue
                    parsed = _parse_timestamp_text(tooltip_value, now)
                    if parsed:
                        return TimestampScrapeResult(
                            parsed, True, "hover_tooltip", tooltip_value
                        )
        except Exception:
            pass
    if relative_fallback is not None:
        return relative_fallback
    return TimestampScrapeResult(None, False, "unavailable", "")


async def _resolved_entity_name(
    surface: Locator, supplied_name: str, page_url: str
) -> str:
    supplied = _fb_normalize_text(supplied_name)
    if supplied:
        return supplied
    actions = surface.locator("[aria-label^='Actions for this post by']")
    for index in range(min(await actions.count(), 5)):
        label = await actions.nth(index).get_attribute("aria-label") or ""
        match = re.match(r"Actions for this post by\s+(.+)$", label, re.IGNORECASE)
        if match:
            return _fb_normalize_text(match.group(1))
    slug = _facebook_page_slug(page_url)
    return unquote(slug).replace("-", " ").strip()


async def _engagement_labels(surface: Locator) -> list[str]:
    try:
        return await surface.locator(
            "[role='button'], [role='link'], [aria-label], a"
        ).evaluate_all(
            """nodes => nodes.filter(node => {
                    const rect = node.getBoundingClientRect();
                    const style = getComputedStyle(node);
                    return rect.width > 0 && rect.height > 0
                        && style.visibility !== 'hidden' && style.display !== 'none';
                }).slice(0, 400).map(node => [
                    node.getAttribute('aria-label') || '',
                    node.getAttribute('title') || '',
                    node.innerText || node.textContent || ''
                ].filter(Boolean).join(' '))"""
        )
    except Exception:
        return []


async def _engagement_action_counts(
    surface: Locator,
) -> dict[str, tuple[int, bool, str]]:
    """Read the count beside Like/Comment/Share in Facebook's action row.

    Reel/permalink layouts render these values as text-only siblings rather than
    accessible labels (for example: ``Like`` + ``2.7K``). Requiring all three
    action kinds in one shallow row prevents a comment's own reaction control
    from being mistaken for post-level engagement.
    """
    try:
        payload = await surface.evaluate(
            """root => {
                const visible = node => {
                    const rect = node.getBoundingClientRect();
                    const style = getComputedStyle(node);
                    return rect.width > 0 && rect.height > 0
                        && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const kind = node => {
                    const label = (node.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (label === 'like' || label === 'react') return 'reactions';
                    if (label === 'comment' || label === 'comments') return 'comments';
                    if (label === 'share' || label === 'shares') return 'shares';
                    return '';
                };
                const buttons = Array.from(root.querySelectorAll('[aria-label]'))
                    .filter(node => visible(node) && kind(node));
                const candidates = new Map();
                for (const button of buttons) {
                    let node = button.parentElement;
                    for (let depth = 1; node && node !== root.parentElement && depth <= 12;
                            depth += 1, node = node.parentElement) {
                        const kinds = new Set(
                            Array.from(node.querySelectorAll('[aria-label]'))
                                .filter(visible).map(kind).filter(Boolean)
                        );
                        if (kinds.has('reactions') && kinds.has('comments') && kinds.has('shares')) {
                            const current = candidates.get(node);
                            if (!current || depth < current.depth) candidates.set(node, {depth});
                            break;
                        }
                        if (node === root) break;
                    }
                }
                const rows = Array.from(candidates.entries()).map(([node, meta]) => ({
                    node,
                    depth: meta.depth,
                    size: node.querySelectorAll('*').length,
                })).sort((a, b) => a.depth - b.depth || a.size - b.size);
                if (!rows.length) return [];
                const row = rows[0].node;
                const results = [];
                for (const branch of Array.from(row.children)) {
                    const branchKinds = new Set(
                        Array.from(branch.querySelectorAll('[aria-label]'))
                            .filter(visible).map(kind).filter(Boolean)
                    );
                    for (const itemKind of branchKinds) {
                        results.push({kind: itemKind, text: (branch.innerText || '').trim()});
                    }
                }
                return results;
            }"""
        )
    except Exception:
        return {}

    counts: dict[str, tuple[int, bool, str]] = {}
    for item in payload or []:
        kind = str(item.get("kind") or "")
        label = _fb_normalize_text(item.get("text"))
        value, exact = _count_info(label)
        if kind in {"reactions", "comments", "shares"} and value is not None:
            previous = counts.get(kind)
            if previous is None or value > previous[0]:
                counts[kind] = (value, exact, label)
    return counts


def _metric_count_info(raw: Any, kind: str) -> tuple[int | None, bool]:
    """Parse the number attached to a specific metric, not any number nearby."""
    text = _fb_normalize_text(raw).translate(_BURMESE_DIGITS)
    metric = r"comments?" if kind == "comments" else r"shares?"
    number = r"([0-9]+(?:[.,][0-9]+)*)\s*([KMB]?)"
    patterns = (
        re.compile(rf"{number}\s*{metric}\b", re.IGNORECASE),
        re.compile(rf"\b{metric}\s*[:\u00b7]\s*{number}", re.IGNORECASE),
    )
    matches: list[tuple[int, bool]] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value, exact = _count_info("".join(match.groups()[-2:]))
            if value is not None:
                matches.append((value, exact))
    return max(matches, key=lambda item: item[0], default=(None, False))


def _aggregate_metric(labels: list[str], kind: str) -> int:
    if kind == "shares":
        tokens = ("share", "shares", "မျှဝေ")
    else:
        tokens = ("comment", "comments", "မှတ်ချက်")
    values = []
    for label in labels:
        lowered = _fb_normalize_text(label).casefold()
        if any(token in lowered for token in tokens):
            value, _ = _metric_count_info(lowered, kind)
            if value is not None:
                values.append(value)
    return max(values, default=0)


def _totals_compatible(known: int, displayed: int, displayed_exact: bool) -> bool:
    """Allow compact display rounding without accepting unrelated DOM counts."""
    if displayed_exact:
        return known == displayed
    tolerance = max(1, round(displayed * 0.05))
    return abs(known - displayed) <= tolerance


def _partial_reaction_payload(
    toolbar: Mapping[str, int],
    displayed_total: int | None,
    displayed_exact: bool,
) -> tuple[dict[str, int | None], bool]:
    """Build a partial payload without publishing cross-contaminated categories."""
    known_sum = sum(toolbar.values())
    raw = _empty_reactions(
        displayed_total if displayed_total is not None else known_sum
    )
    contaminated = (
        displayed_total is not None
        and known_sum > displayed_total
        and not _totals_compatible(known_sum, displayed_total, displayed_exact)
    )
    if not contaminated:
        for key, value in toolbar.items():
            if key in REACTION_KEYS:
                raw[key] = value
    return raw, contaminated


def _reaction_toolbar(labels: list[str]) -> tuple[dict[str, int], bool]:
    counts: dict[str, int] = {}
    exact = True
    for label in labels:
        reaction = _reaction_type(label)
        if not reaction:
            continue
        value, item_exact = _reaction_count_info(label, reaction)
        if value is None:
            continue
        counts[reaction] = max(counts.get(reaction, 0), value)
        exact = exact and item_exact
    return counts, exact


def _summary_total(labels: list[str]) -> tuple[int | None, bool, str]:
    patterns = (
        re.compile(r"(?:all\s+)?reactions?\s*[:·]?\s*([\d၀-၉][\d၀-၉.,]*\s*[KMB]?)", re.I),
        re.compile(r"([\d၀-၉][\d၀-၉.,]*\s*[KMB]?)\s+(?:people\s+)?react", re.I),
    )
    matches_found: list[tuple[int, int, bool, str]] = []
    for label in labels:
        normalized = _fb_normalize_text(label)
        for pattern in patterns:
            match = pattern.search(normalized)
            if match:
                value, exact = _count_info(match.group(1))
                if value is not None:
                    matched_label = _fb_normalize_text(match.group(0))
                    priority = 2 if "all reaction" in matched_label.casefold() else 1
                    matches_found.append((priority, value, exact, matched_label))
    if matches_found:
        _, value, exact, matched_label = max(
            matches_found, key=lambda item: (item[0], item[1])
        )
        return value, exact, matched_label
    return None, False, ""


async def _find_reaction_summary(surface: Locator) -> Locator | None:
    # The aggregate control (for example "All reactions: 87") is the most
    # reliable way to open the breakdown. It is commonly a sibling of, not a
    # child of, the toolbar containing the individual reaction icons.
    candidates = surface.locator("[role='button'], [role='link'], a[aria-label]")
    best: Locator | None = None
    best_score = -1
    for index in range(min(await candidates.count(), 150)):
        candidate = candidates.nth(index)
        try:
            if not await candidate.is_visible():
                continue
        except Exception:
            continue
        label = (await _fb_label(candidate)).casefold()
        value, _, _ = _summary_total([label])
        is_reactor_control = "see who reacted" in label or "who reacted" in label
        if value is None and not is_reactor_control:
            continue
        score = 30 if "all reaction" in label else 15 if is_reactor_control else 10
        if "comment" in label or "share" in label:
            score -= 20
        if score > best_score:
            best, best_score = candidate, score
    if best is not None:
        return best

    toolbars = surface.locator("[role='toolbar']")
    for toolbar_index in range(min(await toolbars.count(), 20)):
        toolbar = toolbars.nth(toolbar_index)
        try:
            if not await toolbar.is_visible():
                continue
        except Exception:
            continue
        toolbar_label = (await _fb_label(toolbar)).casefold()
        if "reacted" not in toolbar_label and "reaction" not in toolbar_label:
            continue
        buttons = toolbar.locator("[role='button']")
        if await buttons.count():
            return buttons.first

    return None


async def _reaction_root_payload(root: Locator) -> dict[str, Any]:
    return await root.evaluate(
        """node => ({
            label: node.getAttribute('aria-label') || '',
            text: (node.innerText || '').slice(0, 12000),
            hasTablist: !!node.querySelector('[role="tablist"]'),
            items: Array.from(node.querySelectorAll(
                '[role="tab"], [role="button"], [role="menuitem"], [aria-label]'
            )).slice(0, 300).map(el => ({
                role: el.getAttribute('role') || '',
                aria: el.getAttribute('aria-label') || '',
                title: el.getAttribute('title') || '',
                text: el.innerText || '',
                alts: Array.from(el.querySelectorAll('img[alt]')).map(img => img.alt).join(' ')
            }))
        })"""
    )


def _parse_reaction_payload(payload: Mapping[str, Any]) -> tuple[dict[str, int], bool]:
    counts: dict[str, int] = {}
    exact = True
    for item in payload.get("items") or []:
        label = _fb_normalize_text(
            " ".join(
                str(item.get(key) or "") for key in ("aria", "title", "text", "alts")
            )
        )
        reaction = _reaction_type(label)
        if not reaction:
            continue
        value, item_exact = _reaction_count_info(label, reaction)
        if value is None:
            continue
        counts[reaction] = max(counts.get(reaction, 0), value)
        exact = exact and item_exact
    return counts, exact


async def _wait_for_reaction_dialog(
    page: Page, marker: str
) -> tuple[Locator | None, dict[str, Any] | None]:
    deadline = time.monotonic() + REACTION_DIALOG_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        dialogs = page.locator(f"div[role='dialog']:not([{marker}='1'])")
        for index in range(await dialogs.count()):
            dialog = dialogs.nth(index)
            try:
                if not await dialog.is_visible():
                    continue
                payload = await _reaction_root_payload(dialog)
            except Exception:
                continue
            label = _fb_normalize_text(payload.get("label")).casefold()
            if label == "loading..." or label == "loading":
                continue
            counts, _ = _parse_reaction_payload(payload)
            reaction_text = (
                _fb_normalize_text(payload.get("label"))
                + " "
                + _fb_normalize_text(payload.get("text"))[:500]
            ).casefold()
            if counts and (
                payload.get("hasTablist")
                or "reaction" in reaction_text
                or len(counts) >= 2
            ):
                return dialog, payload
        await asyncio.sleep(0.2)
    return None, None


async def _close_reaction_overlay(page: Page, marker: str) -> None:
    dialogs = page.locator(f"div[role='dialog']:not([{marker}='1'])")
    for index in range(await dialogs.count()):
        dialog = dialogs.nth(index)
        try:
            if not await dialog.is_visible():
                continue
            close = dialog.get_by_role(
                "button", name=re.compile(r"^(?:Close|ပိတ်)$", re.IGNORECASE)
            )
            if await close.count():
                await close.first.click(timeout=1_500)
        except Exception:
            continue


async def extract_reaction_breakdown(
    page: Page,
    post_surface: Locator,
    displayed_total_hint: tuple[int, bool, str] | None = None,
) -> ReactionScrapeResult:
    started = time.monotonic()
    labels = await _engagement_labels(post_surface)
    try:
        surface_text = await post_surface.inner_text(timeout=2_000)
    except Exception:
        surface_text = ""
    observed_total, observed_exact, observed_label = _summary_total(
        [surface_text, *labels]
    )
    if displayed_total_hint is not None:
        displayed_total, summary_exact, summary_label = displayed_total_hint
    else:
        displayed_total, summary_exact, summary_label = (
            observed_total,
            observed_exact,
            observed_label,
        )
    summary_conflict = (
        displayed_total_hint is not None
        and observed_total is not None
        and not _totals_compatible(observed_total, displayed_total, summary_exact)
    )
    toolbar, toolbar_exact = _reaction_toolbar(labels)
    diagnostics: dict[str, Any] = {
        "status": "unavailable",
        "source": "summary_only",
        "summary_label": summary_label,
        "modal_attempts": 0,
        "modal_opened": False,
        "modal_stalled": False,
        "known_reaction_sum": sum(toolbar.values()),
        "displayed_total": displayed_total,
        "displayed_total_source": "action_row"
        if displayed_total_hint is not None
        else "accessible_summary",
        "observed_summary_total": observed_total,
        "observed_summary_label": observed_label,
        "summary_conflict": summary_conflict,
    }

    if displayed_total == 0:
        diagnostics.update(status="zero", source="summary", termination_reason="zero")
        diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        return ReactionScrapeResult(_zero_reactions(), True, summary_exact, diagnostics)

    if displayed_total is None and not toolbar:
        action_labels = " ".join(labels).casefold()
        if "like" in action_labels and "share" in action_labels:
            diagnostics.update(
                status="zero", source="absent_summary", displayed_total=0,
                termination_reason="no_reactions_present",
            )
            diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            return ReactionScrapeResult(_zero_reactions(), True, True, diagnostics)

    # A conflicting accessible summary normally belongs to a nested comment.
    # Do not click it and accidentally open the comment's reaction breakdown.
    summary = None if summary_conflict else await _find_reaction_summary(post_surface)
    marker = "data-codex-existing-reaction-dialog"
    await page.locator("div[role='dialog']").evaluate_all(
        "(nodes, name) => nodes.forEach(node => node.setAttribute(name, '1'))", marker
    )

    if summary is not None:
        for attempt in range(1, REACTION_DIALOG_ATTEMPTS + 1):
            diagnostics["modal_attempts"] = attempt
            try:
                await summary.scroll_into_view_if_needed(timeout=2_000)
                await summary.click(timeout=4_000)
                dialog, payload = await _wait_for_reaction_dialog(page, marker)
                if dialog is not None and payload is not None:
                    diagnostics["modal_opened"] = True
                    counts, exact = _parse_reaction_payload(payload)
                    if counts:
                        category_sum = sum(counts.values())
                        complete_by_total = displayed_total is None or _totals_compatible(
                            category_sum, displayed_total, summary_exact
                        )
                        if complete_by_total:
                            raw = {
                                **{key: counts.get(key, 0) for key in REACTION_KEYS},
                                "total": category_sum,
                            }
                            diagnostics.update(
                                status="complete_exact" if exact else "complete_compact",
                                source="dialog",
                                known_reaction_sum=category_sum,
                                termination_reason="complete",
                            )
                            await _close_reaction_overlay(page, marker)
                            diagnostics["elapsed_ms"] = int(
                                (time.monotonic() - started) * 1000
                            )
                            return ReactionScrapeResult(raw, True, exact, diagnostics)
                        toolbar.update(counts)
                        toolbar_exact = toolbar_exact and exact
                    await _close_reaction_overlay(page, marker)
            except Exception as exc:
                diagnostics["last_modal_error"] = f"{type(exc).__name__}: {exc}"
            diagnostics["modal_stalled"] = True
            await _close_reaction_overlay(page, marker)
            summary = await _find_reaction_summary(post_surface)
            if summary is None:
                break

    if summary is not None:
        try:
            await summary.hover(timeout=2_000)
            tooltips = page.get_by_role("tooltip")
            for index in range(await tooltips.count()):
                tooltip = tooltips.nth(index)
                if not await tooltip.is_visible():
                    continue
                payload = await _reaction_root_payload(tooltip)
                counts, exact = _parse_reaction_payload(payload)
                if not counts:
                    continue
                known_sum = sum(counts.values())
                if displayed_total is None or _totals_compatible(
                    known_sum, displayed_total, summary_exact
                ):
                    raw = {
                        **{key: counts.get(key, 0) for key in REACTION_KEYS},
                        "total": known_sum,
                    }
                    diagnostics.update(
                        status="complete_exact" if exact else "complete_compact",
                        source="tooltip",
                        known_reaction_sum=known_sum,
                        termination_reason="tooltip_matches_total",
                    )
                    diagnostics["elapsed_ms"] = int(
                        (time.monotonic() - started) * 1000
                    )
                    return ReactionScrapeResult(raw, True, exact, diagnostics)
                toolbar.update(counts)
                toolbar_exact = toolbar_exact and exact
        except Exception as exc:
            diagnostics["tooltip_error"] = f"{type(exc).__name__}: {exc}"

    if toolbar:
        known_sum = sum(toolbar.values())
        if displayed_total is not None and _totals_compatible(
            known_sum, displayed_total, summary_exact
        ):
            raw = {
                **{key: toolbar.get(key, 0) for key in REACTION_KEYS},
                "total": known_sum,
            }
            diagnostics.update(
                status="complete_exact" if toolbar_exact else "complete_compact",
                source="toolbar",
                known_reaction_sum=known_sum,
                termination_reason="toolbar_matches_total",
            )
            diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            return ReactionScrapeResult(raw, True, toolbar_exact, diagnostics)

        # If displayed_total is None but we have toolbar data, check if we have enough reactions
        # Facebook might not show the total in a parseable format
        if displayed_total is None and len(toolbar) >= 5:
            # We have most reaction types from toolbar, consider it complete
            raw = {
                **{key: toolbar.get(key, 0) for key in REACTION_KEYS},
                "total": known_sum,
            }
            diagnostics.update(
                status="complete_compact",
                source="toolbar",
                known_reaction_sum=known_sum,
                termination_reason="toolbar_partial_no_total",
            )
            diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            return ReactionScrapeResult(raw, True, toolbar_exact, diagnostics)

        raw, contaminated = _partial_reaction_payload(
            toolbar, displayed_total, summary_exact
        )
        diagnostics.update(
            status="partial",
            source="toolbar",
            known_reaction_sum=known_sum,
            toolbar_contaminated=contaminated,
            termination_reason="inconsistent_reaction_controls"
            if contaminated
            else "reaction_dialog_stalled",
        )
        diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        return ReactionScrapeResult(raw, False, toolbar_exact, diagnostics)

    raw = _empty_reactions(displayed_total)
    diagnostics.update(
        status="unavailable",
        termination_reason="reaction_summary_unavailable"
        if summary is None
        else "reaction_dialog_stalled",
    )
    diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return ReactionScrapeResult(raw, False, False, diagnostics)


async def scrape_facebook_post(
    page: Page,
    permalink: str,
    page_url: str,
    entity_name: str,
) -> dict[str, Any]:
    # Prefer the already-correlated page-feed container discovered in the same
    # browser state. It is both faster and less ambiguous than Facebook's
    # permalink overlay, whose DOM often retains unrelated background posts.
    surface: Locator | None = None

    async def visible_surface(candidate: Locator | None) -> Locator | None:
        if candidate is None:
            return None
        try:
            return candidate if await candidate.is_visible() else None
        except Exception:
            return None

    try:
        if _normalize_url(page.url) == _normalize_url(page_url):
            surface = await visible_surface(
                await _locate_post_surface(page, permalink, timeout_seconds=3.0)
            )
    except RuntimeError:
        surface = None

    if surface is None:
        surface = await visible_surface(
            await _recover_post_surface_from_feed(page, page_url, permalink)
        )

    if surface is None:
        await _goto_recoverable(page, permalink)
        await _dismiss_facebook_overlays(page)
        interruption = await _detect_interruption(page)
        if interruption:
            raise RuntimeError(f"Facebook interruption: {interruption}")
        surface = await visible_surface(await _locate_post_surface(page, permalink))
        if surface is None:
            raise RuntimeError(
                "Facebook rendered only a hidden/stale copy of the target post"
            )

    now = datetime.now(FACEBOOK_TIMEZONE)
    platform_id = _platform_content_id(permalink)
    post_text = ""
    labels: list[str] = []
    action_counts: dict[str, tuple[int, bool, str]] = {}
    for _ in range(3):
        candidate_text = await _extract_post_text(surface)
        candidate_labels = await _engagement_labels(surface)
        candidate_action_counts = await _engagement_action_counts(surface)
        if candidate_text:
            post_text = candidate_text
        if candidate_labels:
            labels = candidate_labels
        if candidate_action_counts:
            action_counts = candidate_action_counts
        action_text = " ".join(labels).casefold()
        if post_text and (
            "like" in action_text
            or "share" in action_text
            or bool(action_counts)
        ):
            break
        await asyncio.sleep(0.4)
    if surface is None:
        raise RuntimeError("Facebook post surface disappeared during extraction")

    total_shares = action_counts.get("shares", (None, False, ""))[0]
    if total_shares is None:
        total_shares = _aggregate_metric(labels, "shares")
    total_comments = action_counts.get("comments", (None, False, ""))[0]
    if total_comments is None:
        total_comments = _aggregate_metric(labels, "comments")
    timestamp_result = await _extract_timestamp(surface, now)
    post_timestamp = timestamp_result.value
    reaction_result = await extract_reaction_breakdown(
        page,
        surface,
        displayed_total_hint=action_counts.get("reactions"),
    )

    try:
        grouped = compute_reaction_metrics(reaction_result.raw_reactions)
    except ValueError as exc:
        reaction_result.complete = False
        reaction_result.diagnostics.update(
            status="partial", metrics_error=str(exc), termination_reason="invalid_metrics"
        )
        grouped = _null_grouped_reactions()

    identity = platform_id or _normalize_url(permalink) or (
        hashlib.sha256(
            f"{post_text}\x1f{post_timestamp.isoformat() if post_timestamp else ''}".encode()
        ).hexdigest()
    )
    resolved_entity_name = await _resolved_entity_name(
        surface, entity_name, page_url
    )
    content_hash = _content_hash(post_text, post_timestamp)
    return {
        "_id": _scoped_post_id(page_url, identity),
        "source_type": "Social",
        "platform": "facebook",
        "entity_name": resolved_entity_name,
        "page_url": _normalize_url(page_url),
        "post_permalink": permalink,
        "platform_content_id": platform_id,
        "identity_source": "permalink" if platform_id else "permalink_hash",
        "content_hash": content_hash,
        "title_or_post": post_text,
        "post_timestamp": post_timestamp,
        "post_timestamp_exact": timestamp_result.exact,
        "post_timestamp_source": timestamp_result.source,
        "post_timestamp_label": timestamp_result.observed_label,
        "reactions_breakdown": reaction_result.raw_reactions,
        "grouped_reactions": grouped,
        "reactions_breakdown_complete": reaction_result.complete,
        "reactions_breakdown_exact": reaction_result.exact,
        "reaction_diagnostics": reaction_result.diagnostics,
        "total_shares": total_shares,
        "total_comments": total_comments,
    }


def _persist_facebook_documents(db, documents: list[dict[str, Any]]) -> dict[str, int]:
    if not documents:
        return {"inserted": 0, "modified": 0}
    now = datetime.now()
    operations = []
    obsolete_fields = {
        "total_reactions": "",
        "feedbacks": "",
        "comments_complete": "",
        "comment_diagnostics": "",
        "comment_count": "",
        "latest_comment_attempt_at": "",
        "last_successful_comments_at": "",
        "comment_retry_count": "",
        "comment_retry_status": "",
        "next_comment_retry_at": "",
        "latest_attempted_total_reactions": "",
        "latest_attempted_total_shares": "",
        "latest_attempted_total_comments": "",
        "latest_attempted_comment_count": "",
    }
    for document in documents:
        try:
            document["grouped_reactions"] = compute_reaction_metrics(
                document["reactions_breakdown"]
            )
        except ValueError as exc:
            document["grouped_reactions"] = _null_grouped_reactions()
            document["reactions_breakdown_complete"] = False
            document.setdefault("reaction_diagnostics", {}).update(
                status="partial", metrics_error=str(exc),
                termination_reason="invalid_metrics",
            )
        existing = None
        platform_id = document.get("platform_content_id")
        if platform_id:
            existing = db.contents.find_one(
                {"source_type": "Social", "platform_content_id": platform_id}, {"_id": 1}
            )
        if not existing:
            content_hash = document.get("content_hash")
            if content_hash:
                existing = db.contents.find_one(
                    {"source_type": "Social", "content_hash": content_hash}, {"_id": 1}
                )
        document_id = existing["_id"] if existing else document["_id"]
        snapshot = {
            "scraped_at": now,
            "reactions_breakdown": document["reactions_breakdown"],
            "grouped_reactions": document["grouped_reactions"],
            "reactions_breakdown_complete": document["reactions_breakdown_complete"],
            "reactions_breakdown_exact": document["reactions_breakdown_exact"],
            "shares": document["total_shares"],
            "comments": document["total_comments"],
        }
        content_set = {key: value for key, value in document.items() if key != "_id"}
        content_set.update(last_updated_at=now, lifecycle_status="tracking")
        operations.append(
            UpdateOne(
                {"_id": document_id},
                {
                    "$set": content_set,
                    "$setOnInsert": {
                        "first_scraped_at": now,
                        "expires_at": now + timedelta(days=LIFECYCLE_DAYS),
                    },
                    "$inc": {"scrape_count": 1},
                    "$push": {
                        "engagement_history": {
                            "$each": [snapshot],
                            "$slice": -MAX_ENGAGEMENT_HISTORY,
                        }
                    },
                    "$unset": obsolete_fields,
                },
                upsert=True,
            )
        )
    result = db.contents.bulk_write(operations, ordered=False)
    return {"inserted": result.upserted_count, "modified": result.modified_count}


def _facebook_json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_facebook_json(path: str, documents: list[dict[str, Any]]) -> None:
    """Atomically publish partial progress so a later browser error loses nothing."""
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(
            documents,
            handle,
            ensure_ascii=False,
            indent=2,
            default=_facebook_json_default,
        )
    os.replace(temporary_path, path)


def _write_facebook_report(path: str, report: dict[str, Any]) -> None:
    """Atomically replace the per-run diagnostic report, including failures."""
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(
            report,
            handle,
            ensure_ascii=False,
            indent=2,
            default=_facebook_json_default,
        )
    os.replace(temporary_path, path)


async def _capture_facebook_debug_screenshot(
    page: Page, cookie_path: str, prefix: str
) -> str | None:
    debug_dir = os.path.join(os.path.dirname(cookie_path), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    screenshot_path = os.path.join(debug_dir, f"{prefix}_{int(time.time())}.png")
    try:
        await page.screenshot(path=screenshot_path)
    except Exception:
        return None
    print(f"[DEBUG] Screenshot saved: {screenshot_path}")
    return screenshot_path


async def run_facebook_page_scrape(
    db,
    page_url: str,
    entity_name: str,
    max_posts: int,
    cookie_path: str,
    headless: bool,
) -> list[dict[str, Any]]:
    print(f"\n[INFO] Scraping Facebook post metadata: {page_url}")
    
    total_cookies, valid_cookies, cookie_warnings = _validate_facebook_cookies(cookie_path)
    print(f"[INFO] Cookie validation: {valid_cookies}/{total_cookies} valid cookies")
    for warning in cookie_warnings:
        print(f"[WARN] {warning}")
    
    if valid_cookies == 0:
        raise RuntimeError(
            f"No valid Facebook cookies found in {cookie_path}. "
            "Export fresh cookies after signing in to Facebook."
        )
    
    documents: list[dict[str, Any]] = []
    post_errors: list[dict[str, Any]] = []
    persistence = {"inserted": 0, "modified": 0}
    debug_dir = os.path.dirname(cookie_path)
    debug_path = os.path.join(debug_dir, "facebook_data.json")
    report_path = os.path.join(debug_dir, "facebook_run_report.json")
    _write_facebook_json(debug_path, documents)
    _write_facebook_report(
        report_path,
        {
            "status": "running",
            "page_url": page_url,
            "requested_posts": max_posts,
            "discovered_posts": 0,
            "saved_documents": 0,
            "mongo": persistence,
            "errors": [],
        },
    )
    await asyncio.to_thread(
        db.contents.update_many,
        {
            "source_type": "Social",
            "lifecycle_status": "tracking",
            "expires_at": {"$lte": datetime.now()},
        },
        {"$set": {"lifecycle_status": "final", "finalized_at": datetime.now()}},
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(
            locale="en-US", timezone_id=FACEBOOK_TIMEZONE_NAME
        )
        try:
            loaded = await _load_cookies(context, cookie_path)
            print(f"[INFO] Loaded {loaded} Facebook cookies into browser.")
            page = await context.new_page()
            
            await _goto_recoverable(page, page_url)
            await _dismiss_facebook_overlays(page)

            interruption = await _detect_interruption(page)
            if interruption:
                message = _facebook_interruption_message(interruption, page_url)
                screenshot_path = await _capture_facebook_debug_screenshot(
                    page, cookie_path, f"facebook_{interruption}"
                )
                _write_facebook_report(
                    report_path,
                    {
                        "status": "failed",
                        "page_url": page_url,
                        "requested_posts": max_posts,
                        "discovered_posts": 0,
                        "saved_documents": 0,
                        "mongo": persistence,
                        "errors": [{"phase": "page_open", "error": message}],
                        "debug_screenshot": screenshot_path,
                    },
                )
                raise RuntimeError(message)
            
            authenticated = await _is_authenticated(page)
            if not authenticated:
                screenshot_path = await _capture_facebook_debug_screenshot(
                    page, cookie_path, "auth_failed"
                )
                message = (
                    "Facebook authentication failed. The cookies in cookies.json are expired or invalid. "
                    "Sign in to Facebook in your browser and export fresh cookies."
                )
                _write_facebook_report(
                    report_path,
                    {
                        "status": "failed",
                        "page_url": page_url,
                        "requested_posts": max_posts,
                        "discovered_posts": 0,
                        "saved_documents": 0,
                        "mongo": persistence,
                        "errors": [{"phase": "authentication", "error": message}],
                        "debug_screenshot": screenshot_path,
                    },
                )
                raise RuntimeError(message)
            
            print("[INFO] Facebook authentication successful.")
            try:
                permalinks = await _discover_post_permalinks(
                    page, page_url, max_posts
                )
            except Exception as exc:
                screenshot_path = await _capture_facebook_debug_screenshot(
                    page, cookie_path, "discovery_failed"
                )
                _write_facebook_report(
                    report_path,
                    {
                        "status": "failed",
                        "page_url": page_url,
                        "requested_posts": max_posts,
                        "discovered_posts": 0,
                        "saved_documents": 0,
                        "mongo": persistence,
                        "errors": [
                            {
                                "phase": "discovery",
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        ],
                        "debug_screenshot": screenshot_path,
                    },
                )
                raise
            
            if not permalinks:
                screenshot_path = await _capture_facebook_debug_screenshot(
                    page, cookie_path, "no_posts"
                )
                interruption = await _detect_interruption(page)
                message = (
                    _facebook_interruption_message(interruption, page_url)
                    if interruption
                    else (
                    "Facebook did not render any post permalinks after multiple attempts. "
                        "The page may have no public posts or Facebook may have "
                        "temporarily changed its feed response."
                    )
                )
                _write_facebook_report(
                    report_path,
                    {
                        "status": "failed",
                        "page_url": page_url,
                        "requested_posts": max_posts,
                        "discovered_posts": 0,
                        "saved_documents": 0,
                        "mongo": persistence,
                        "errors": [{"phase": "discovery", "error": message}],
                        "debug_screenshot": screenshot_path,
                    },
                )
                raise RuntimeError(message)
            
            print(f"[INFO] Discovered {len(permalinks)} unique post permalink(s).")
            if len(permalinks) < max_posts:
                print(
                    f"[WARN] Requested {max_posts} posts, but Facebook exposed only "
                    f"{len(permalinks)} in this browser session."
                )
            
            for index, permalink in enumerate(permalinks, 1):
                try:
                    platform_id = _platform_content_id(permalink)
                    final_id_clauses = [
                        {"_id": _scoped_post_id(
                            page_url, platform_id or _normalize_url(permalink)
                        )}
                    ]
                    if platform_id:
                        final_id_clauses.append({"platform_content_id": platform_id})
                    final_query = {
                        "source_type": "Social",
                        "lifecycle_status": "final",
                        "$or": final_id_clauses,
                    }
                    existing_final = await asyncio.to_thread(
                        db.contents.find_one, final_query
                    )
                    if existing_final:
                        print(f"   -> Post {index}/{len(permalinks)}: finalized; skipped.")
                        existing_final["feed_position"] = index
                        documents.append(existing_final)
                        _write_facebook_json(debug_path, documents)
                        continue
                    document = await scrape_facebook_post(
                        page, permalink, page_url, entity_name
                    )
                    document["feed_position"] = index
                    documents.append(document)
                    _write_facebook_json(debug_path, documents)
                    saved = await asyncio.to_thread(
                        _persist_facebook_documents, db, [document]
                    )
                    persistence["inserted"] += saved["inserted"]
                    persistence["modified"] += saved["modified"]
                    reaction_status = document["reaction_diagnostics"].get("status")
                    print(
                        f"   -> Post {index}/{len(permalinks)}: "
                        f"{document['reactions_breakdown'].get('total')} reactions "
                        f"({reaction_status})"
                    )
                except Exception as exc:
                    error_msg = f"{type(exc).__name__}: {exc}"
                    post_errors.append(
                        {"index": index, "permalink": permalink, "error": error_msg}
                    )
                    print(f"   -> [WARN] Post {index} skipped: {error_msg}")
            
            if post_errors and not documents:
                error_summary = "\n".join(
                    f"  Post {item['index']}: {item['error']}"
                    for item in post_errors[:5]
                )
                _write_facebook_report(
                    report_path,
                    {
                        "status": "failed",
                        "page_url": page_url,
                        "requested_posts": max_posts,
                        "discovered_permalinks": permalinks,
                        "discovered_posts": len(permalinks),
                        "saved_documents": 0,
                        "mongo": persistence,
                        "errors": post_errors,
                    },
                )
                raise RuntimeError(
                    f"All {len(post_errors)} post(s) failed to scrape:\n{error_summary}"
                )
        finally:
            await context.close()
            await browser.close()

    print(
        f"[MONGO] Facebook contents: {persistence['inserted']} inserted, "
        f"{persistence['modified']} updated; no Facebook comments written."
    )
    _write_facebook_json(debug_path, documents)
    _write_facebook_report(
        report_path,
        {
            "status": "completed" if not post_errors else "partial",
            "page_url": page_url,
            "requested_posts": max_posts,
            "discovered_posts": len(permalinks),
            "saved_documents": len(documents),
            "mongo": persistence,
            "errors": post_errors,
        },
    )
    print(f"[JSON] Wrote {len(documents)} document(s) to {debug_path}")
    return documents


_OBSOLETE_FACEBOOK_FIELDS = (
    "total_reactions",
    "feedbacks",
    "comments_complete",
    "comment_diagnostics",
    "comment_count",
    "latest_comment_attempt_at",
    "last_successful_comments_at",
    "comment_retry_count",
    "comment_retry_status",
    "next_comment_retry_at",
    "latest_attempted_total_reactions",
    "latest_attempted_total_shares",
    "latest_attempted_total_comments",
    "latest_attempted_comment_count",
)


def _legacy_breakdown(total: Any) -> dict[str, int | None]:
    value = total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None
    return {**{key: None for key in REACTION_KEYS}, "total": value}


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            pass
    return datetime.min


def _migration_metrics(raw: Mapping[str, int | None]) -> tuple[dict[str, Any], bool]:
    try:
        return compute_reaction_metrics(raw), True
    except ValueError:
        return _null_grouped_reactions(), False


def migrate_facebook_schema(db, confirm_delete: bool = False) -> dict[str, Any]:
    """Dry-run by default; destructively migrate only when confirm_delete is true."""
    query = {
        "$or": [
            {"platform": "facebook"},
            {"source_type": "Social", "_id": {"$regex": "^fb_post_"}},
        ]
    }
    documents = list(db.contents.find(query))
    content_ids = [document["_id"] for document in documents]
    feedback_query = {"content_id": {"$in": content_ids}} if content_ids else {"_id": None}
    report = {
        "dry_run": not confirm_delete,
        "facebook_contents": len(documents),
        "facebook_feedbacks_to_delete": db.feedbacks.count_documents(feedback_query),
        "duplicate_documents_removed": 0,
        "contents_modified": 0,
    }
    if not confirm_delete:
        return report

    db.feedbacks.delete_many(feedback_query)
    for document in documents:
        update_set: dict[str, Any] = {"platform": "facebook"}
        if not isinstance(document.get("reactions_breakdown"), dict):
            raw = _legacy_breakdown(document.get("total_reactions"))
            update_set["reactions_breakdown_complete"] = False
            update_set["reactions_breakdown_exact"] = False
        else:
            raw = {
                **{key: document["reactions_breakdown"].get(key) for key in REACTION_KEYS},
                "total": document["reactions_breakdown"].get("total"),
            }
        grouped, metrics_valid = _migration_metrics(raw)
        update_set["reactions_breakdown"] = raw
        update_set["grouped_reactions"] = grouped
        if not metrics_valid:
            update_set["reactions_breakdown_complete"] = False

        migrated_history = []
        for snapshot in document.get("engagement_history", []):
            snapshot = dict(snapshot)
            if not isinstance(snapshot.get("reactions_breakdown"), dict):
                raw = _legacy_breakdown(snapshot.pop("reactions", None))
                snapshot["reactions_breakdown_complete"] = False
                snapshot["reactions_breakdown_exact"] = False
            else:
                raw = {
                    **{key: snapshot["reactions_breakdown"].get(key) for key in REACTION_KEYS},
                    "total": snapshot["reactions_breakdown"].get("total"),
                }
            grouped, metrics_valid = _migration_metrics(raw)
            snapshot["reactions_breakdown"] = raw
            snapshot["grouped_reactions"] = grouped
            if not metrics_valid:
                snapshot["reactions_breakdown_complete"] = False
            migrated_history.append(snapshot)
        if migrated_history:
            update_set["engagement_history"] = migrated_history[-MAX_ENGAGEMENT_HISTORY:]

        result = db.contents.update_one(
            {"_id": document["_id"]},
            {
                "$set": update_set,
                "$unset": {field: "" for field in _OBSOLETE_FACEBOOK_FIELDS},
            },
        )
        report["contents_modified"] += result.modified_count

    groups: dict[str, list[dict[str, Any]]] = {}
    refreshed = list(db.contents.find(query))
    for document in refreshed:
        platform_id = _fb_normalize_text(document.get("platform_content_id"))
        if platform_id:
            groups.setdefault(platform_id, []).append(document)
    for duplicates in groups.values():
        if len(duplicates) < 2:
            continue
        duplicates.sort(key=lambda item: _datetime_value(item.get("last_updated_at")), reverse=True)
        survivor, *losers = duplicates
        history = []
        for item in duplicates:
            history.extend(item.get("engagement_history", []))
        history.sort(key=lambda item: _datetime_value(item.get("scraped_at")))
        first_scraped_values = [
            item.get("first_scraped_at")
            for item in duplicates
            if item.get("first_scraped_at")
        ]
        first_scraped = min(first_scraped_values, key=_datetime_value) \
            if first_scraped_values else survivor.get("first_scraped_at")
        db.contents.update_one(
            {"_id": survivor["_id"]},
            {
                "$set": {
                    "engagement_history": history[-MAX_ENGAGEMENT_HISTORY:],
                    "first_scraped_at": first_scraped,
                    "scrape_count": sum(int(item.get("scrape_count", 0) or 0) for item in duplicates),
                },
            },
        )
        loser_ids = [item["_id"] for item in losers]
        db.contents.delete_many({"_id": {"$in": loser_ids}})
        report["duplicate_documents_removed"] += len(loser_ids)

    for index in list(db.contents.list_indexes()):
        keys = dict(index.get("key", {}))
        if "comments_complete" in keys or "next_comment_retry_at" in keys:
            db.contents.drop_index(index["name"])
    db.contents.create_index(
        [("source_type", 1), ("platform_content_id", 1)],
        name="facebook_platform_content_unique",
        unique=True,
        partialFilterExpression={
            "platform": "facebook",
            "platform_content_id": {"$type": "string", "$gt": ""},
        },
    )
    return report
