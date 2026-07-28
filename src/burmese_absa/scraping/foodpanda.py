"""
Foodpanda review scraping (Playwright sync) and review extraction.

Constants used here (FOODPANDA_*) live in `_config.py`.
Text helpers (normalize_foodpanda_*, parse_foodpanda_relative_time) live
in `_common.py` and are re-imported here for convenience.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import unquote, urlparse, urlunparse

from ._common import (
    normalize_foodpanda_rating,
    normalize_foodpanda_text,
    parse_foodpanda_relative_time,
    parse_relative_time,
)
from ._config import (
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
)
from .storage import add_feedback, get_or_create_content

__all__ = [
    "FOODPANDA_REVIEW_MODAL",
    "FOODPANDA_REVIEW_CARDS",
    "FOODPANDA_REVIEW_LABEL_RE",
    "FOODPANDA_MORE_LABEL_RE",
    "FOODPANDA_NAVIGATION_TIMEOUT_MS",
    "FOODPANDA_ACTION_TIMEOUT_MS",
    "FOODPANDA_MAX_STEPS",
    "FOODPANDA_STALE_LIMIT",
    "FOODPANDA_SCROLL_WAIT_MS",
    "FOODPANDA_RESPONSE_HINTS",
    "FOODPANDA_OVERALL_RATING",
    "FOODPANDA_UI_CHROME_RE",
    "FOODPANDA_GENERIC_AUTHORS",
    "is_foodpanda_modal_open",
    "foodpanda_review_modal_locator",
    "wait_for_foodpanda_review_modal",
    "is_real_foodpanda_review",
    "normalize_foodpanda_record",
    "find_foodpanda_review_objects",
    "collect_foodpanda_review_response",
    "dismiss_foodpanda_overlays",
    "extract_foodpanda_overall_rating",
    "foodpanda_dom_signature",
    "open_foodpanda_review_surface",
    "mounted_foodpanda_reviews",
    "foodpanda_review_id",
    "harvest_foodpanda_records",
    "exhaust_foodpanda_reviews",
    "derive_foodpanda_entity_name",
    "scrape_foodpanda_reviews",
    "scrape_business_blog",
    "foodpanda_reviews_url",
    "canonical_foodpanda_shop_url",
]

def _first_value(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, '', [], {}):
            return value
    return None


def foodpanda_reviews_url(shop_url):
    """Return the shop URL with a /reviews suffix for the reviews modal route."""
    parsed = urlparse(normalize_foodpanda_text(shop_url))
    path = parsed.path.rstrip('/')
    if path.casefold().endswith('/reviews'):
        return shop_url
    return urlunparse(parsed._replace(path=f'{path}/reviews'))


def canonical_foodpanda_shop_url(shop_url):
    parsed = urlparse(normalize_foodpanda_text(shop_url))
    path = parsed.path.rstrip('/')
    if path.casefold().endswith('/reviews'):
        path = path[:-len('/reviews')]
    path = path.rstrip('/') or '/'
    return urlunparse(parsed._replace(path=path, query='', fragment=''))


def foodpanda_review_modal_locator(page):
    return page.locator(FOODPANDA_REVIEW_MODAL).first


def is_foodpanda_modal_open(page):
    try:
        modal = foodpanda_review_modal_locator(page)
        return modal.count() > 0 and modal.is_visible()
    except Exception:
        return False


def wait_for_foodpanda_review_modal(page, timeout_ms=12000):
    try:
        modal = foodpanda_review_modal_locator(page)
        modal.wait_for(state='visible', timeout=timeout_ms)
        modal.locator(FOODPANDA_REVIEW_CARDS).first.wait_for(state='attached', timeout=timeout_ms)
        return True
    except Exception:
        return is_foodpanda_modal_open(page)


def is_real_foodpanda_review(record, source='dom'):
    if not record:
        return False
    text = normalize_foodpanda_text(record.get('text'))
    if not text or FOODPANDA_REVIEW_LABEL_RE.fullmatch(text):
        return False
    if FOODPANDA_UI_CHROME_RE.fullmatch(text):
        return False
    author = normalize_foodpanda_text(record.get('author'))
    date = normalize_foodpanda_text(record.get('date'))
    rating_known = record.get('rating') is not None
    author_known = author and author.casefold() not in FOODPANDA_GENERIC_AUTHORS
    date_known = bool(date)
    if source == 'dom':
        return (author_known or date_known or rating_known) and len(text) >= 3
    return (author_known or date_known or rating_known) and len(text) >= 3


def normalize_foodpanda_record(record):
    if not isinstance(record, dict):
        return None
    text = normalize_foodpanda_text(_first_value(
        record, ('text', 'comment', 'content', 'review_text', 'reviewText', 'description', 'body')))
    if not text:
        return None
    author_value = _first_value(record, ('author', 'user_name', 'userName', 'customer_name', 'customerName', 'reviewer'))
    if isinstance(author_value, dict):
        author_value = _first_value(author_value, ('name', 'display_name', 'displayName'))
    return {
        'id': normalize_foodpanda_text(_first_value(record, ('id', 'review_id', 'reviewId', 'uuid'))),
        'author': normalize_foodpanda_text(author_value) or 'Unknown',
        'date': normalize_foodpanda_text(_first_value(
            record, ('date', 'created_at', 'createdAt', 'timestamp', 'submitted_at'))),
        'rating': normalize_foodpanda_rating(_first_value(
            record, ('rating', 'stars', 'score', 'rating_value', 'ratingValue'))),
        'text': text,
    }


def find_foodpanda_review_objects(payload):
    """Find review-shaped objects; an arbitrary API `message` is never review text."""
    found = []
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(current)
            continue
        if not isinstance(current, dict):
            continue
        text_keys = {'text', 'comment', 'content', 'review_text', 'reviewText', 'description', 'body'}
        evidence_keys = {
            'id', 'review_id', 'reviewId', 'uuid', 'author', 'user_name', 'userName',
            'customer_name', 'customerName', 'reviewer', 'date', 'created_at',
            'createdAt', 'timestamp', 'submitted_at', 'rating', 'stars', 'score',
            'rating_value', 'ratingValue'
        }
        if text_keys.intersection(current) and evidence_keys.intersection(current):
            normalized = normalize_foodpanda_record(current)
            if normalized:
                found.append(normalized)
        stack.extend(value for value in current.values() if isinstance(value, (dict, list)))
    return found


def collect_foodpanda_review_response(response, state):
    url = normalize_foodpanda_text(getattr(response, 'url', '')).casefold()
    if not any(hint in url for hint in FOODPANDA_RESPONSE_HINTS):
        return
    state['matching_responses'] = state.get('matching_responses', 0) + 1
    try:
        if hasattr(response, 'ok') and not response.ok:
            return
        records = find_foodpanda_review_objects(response.json())
    except Exception:
        state['response_errors'] = state.get('response_errors', 0) + 1
        return
    known = state.setdefault('_record_keys', set())
    for record in records:
        key = json.dumps(record, sort_keys=True, ensure_ascii=False)
        if key not in known:
            known.add(key)
            state.setdefault('records', []).append(record)
    state['api_objects'] = len(state.get('records', []))


def dismiss_foodpanda_overlays(page):
    result = {'actions': 0, 'blocker_remaining': False}
    labels = re.compile(r'accept|agree|allow|continue|not now|close|skip|got it|လက်ခံ|ပိတ်', re.I)
    for selector in ("button", "[role='button']"):
        controls = page.locator(selector).filter(has_text=labels)
        for index in range(min(controls.count(), 12)):
            try:
                item = controls.nth(index)
                if item.is_visible() and item.bounding_box():
                    item.click(timeout=FOODPANDA_ACTION_TIMEOUT_MS)
                    result['actions'] += 1
                    break
            except Exception:
                continue
    try:
        blockers = page.locator(
            "[role='dialog']:visible, [aria-modal='true']:visible, "
            "[data-testid*='location' i]:visible"
        )
        result['blocker_remaining'] = blockers.count() > 0
    except Exception:
        pass
    return result


def extract_foodpanda_overall_rating(page):
    """Read the shop's overall rating from the reviews modal summary section."""
    if not is_foodpanda_modal_open(page):
        return None
    try:
        modal = foodpanda_review_modal_locator(page)
        score = normalize_foodpanda_text(modal.locator(FOODPANDA_OVERALL_RATING).first.inner_text())
        return normalize_foodpanda_rating(score)
    except Exception:
        return None


def foodpanda_dom_signature(page):
    try:
        root = foodpanda_review_modal_locator(page) if is_foodpanda_modal_open(page) else page.locator('body')
        values = root.locator(FOODPANDA_REVIEW_CARDS).all_text_contents()
    except Exception:
        values = []
    canonical = '\x1e'.join(normalize_foodpanda_text(value) for value in values if normalize_foodpanda_text(value))
    return canonical


def open_foodpanda_review_surface(page, response_state, shop_url=None):
    result = {'found': False, 'opened': False, 'reason': 'review_control_not_found', 'modal_opened': False}
    if is_foodpanda_modal_open(page):
        result.update(found=True, opened=True, modal_opened=True, reason='review_surface_already_visible')
        return result
    if shop_url:
        reviews_url = foodpanda_reviews_url(shop_url)
        if normalize_foodpanda_text(page.url).casefold() != normalize_foodpanda_text(reviews_url).casefold():
            try:
                page.goto(reviews_url, wait_until='domcontentloaded', timeout=FOODPANDA_NAVIGATION_TIMEOUT_MS)
                dismiss_foodpanda_overlays(page)
            except Exception as exc:
                result['reason'] = f'reviews_url_navigation_error:{type(exc).__name__}'
        if wait_for_foodpanda_review_modal(page):
            result.update(found=True, opened=True, modal_opened=True, reason='reviews_url_opened')
            return result
    try:
        existing = foodpanda_review_modal_locator(page).locator(FOODPANDA_REVIEW_CARDS)
        if existing.count() > 0 and existing.first.is_visible():
            result.update(found=True, opened=True, modal_opened=True, reason='review_surface_already_visible')
            return result
    except Exception:
        pass
    selectors = (
        "main [data-testid*='review' i], main [data-test-id*='review' i], "
        "main button, main a, main [role='button']"
    )
    controls = page.locator(selectors)
    for index in range(min(controls.count(), 80)):
        try:
            control = controls.nth(index)
            label = normalize_foodpanda_text(control.inner_text()) + ' ' + normalize_foodpanda_text(
                control.get_attribute('aria-label'))
            if not FOODPANDA_REVIEW_LABEL_RE.search(label) or not control.is_visible():
                continue
            result['found'] = True
            before_signature = foodpanda_dom_signature(page)
            before_api = len(response_state.get('records', []))
            control.click(timeout=FOODPANDA_ACTION_TIMEOUT_MS)
            try:
                page.wait_for_function(
                    "([selector, old]) => { const nodes=[...document.querySelectorAll(selector)]; "
                    "return nodes.some(n => (n.innerText||'').trim()) && "
                    "nodes.map(n => (n.innerText||'').replace(/\\s+/g, ' ').trim()).filter(Boolean).join('\\x1e') !== old; }",
                    arg=[FOODPANDA_REVIEW_CARDS, before_signature], timeout=8000)
            except Exception:
                pass
            if foodpanda_dom_signature(page) != before_signature or len(response_state.get('records', [])) > before_api:
                result.update(opened=True, modal_opened=wait_for_foodpanda_review_modal(page, timeout_ms=4000),
                              reason='review_surface_detected')
            else:
                result.update(opened=True, modal_opened=wait_for_foodpanda_review_modal(page, timeout_ms=4000),
                              reason='review_control_clicked_unconfirmed')
            return result
        except Exception as exc:
            result['reason'] = f'review_control_error:{type(exc).__name__}'
    return result


def _dom_card_record(card):
    """Extract a review record from a foodpanda review card DOM element.

    Selectors are ordered: foodpanda Myanmar data-testid first, then generic
    fallbacks so the code works across foodpanda country sites.
    """
    data = card.evaluate("""(node) => {
        const pick = (selectors) => {
            for (const s of selectors) {
                const e = node.querySelector(s);
                if (e && (e.innerText||e.textContent||'').trim())
                    return (e.innerText||e.textContent||'').trim();
            }
            return '';
        };

        // ── Author name ──
        const author = pick([
            '[data-testid="info-reviews-modal-reviewer-name"]',
            '[data-testid*="reviewer-name"] p',
            '[data-testid*="reviewer-name"]',
            '[class*="reviewer-name"] p',
            '[class*="reviewer-name"]'
        ]);

        // ── Review text ──
        const text = pick([
            '[data-testid="info-reviews-modal-description"]',
            '[data-testid*="reviews-modal-description"]',
            'p[class*="description"]'
        ]);

        // ── Date ──
        const date = pick([
            '[data-testid="info-reviews-modal-review-date"]',
            '[data-testid*="review-date"]',
            'p[class*="review-date"]',
            'time'
        ]);

        // ── Review ID ──
        const id = node.getAttribute('data-review-id') ||
            node.getAttribute('data-id') || '';

        return { id, text, author, date };
    }""") or {}
    return normalize_foodpanda_record(data)


def mounted_foodpanda_reviews(page, stats=None):
    stats = stats if stats is not None else {}
    records = []
    stats['legacy_nodes'] = 0
    if not is_foodpanda_modal_open(page):
        stats['dom_cards'] = 0
        stats['dom_records'] = 0
        return records
    modal = foodpanda_review_modal_locator(page)
    cards = modal.locator(FOODPANDA_REVIEW_CARDS)
    stats['dom_cards'] = cards.count()
    for index in range(cards.count()):
        try:
            record = _dom_card_record(cards.nth(index))
            if record and is_real_foodpanda_review(record, source='dom'):
                records.append(record)
            elif record:
                stats['rejected_records'] = stats.get('rejected_records', 0) + 1
        except Exception:
            stats['dom_parse_failures'] = stats.get('dom_parse_failures', 0) + 1
    stats['dom_records'] = len(records)
    return records


def foodpanda_review_id(shop_id, record):
    platform_id = normalize_foodpanda_text(record.get('id'))
    if platform_id:
        safe_id = re.sub(r'[^\w.-]+', '_', platform_id, flags=re.UNICODE)
        return f'fp_rev_{safe_id}'
    parts = [shop_id, record.get('author', ''), record.get('date', ''), record.get('text', '')]
    canonical = '\x1f'.join(normalize_foodpanda_text(value) for value in parts)
    return 'fp_rev_' + hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def harvest_foodpanda_records(content_obj, records, seen_ids, shop_id, source='dom', stats=None):
    added = 0
    stats = stats if stats is not None else {}
    existing = {fb.get('id') or fb.get('source_feedback_id') for fb in content_obj.get('feedbacks', [])}
    for raw_record in records:
        record = normalize_foodpanda_record(raw_record)
        if not record:
            continue
        if not is_real_foodpanda_review(record, source=source):
            stats['rejected_records'] = stats.get('rejected_records', 0) + 1
            continue
        feedback_id = foodpanda_review_id(shop_id, record)
        if feedback_id in seen_ids or feedback_id in existing:
            continue
        seen_ids.add(feedback_id)
        existing.add(feedback_id)
        content_obj['feedbacks'].append({
            'id': feedback_id, 'source_feedback_id': feedback_id,
            'platform_review_id': record.get('id') or '',
            'source': source,
            'author': record.get('author') or 'Unknown',
            'text': record['text'], 'raw_text': record['text'],
            'rating': record.get('rating'),
            'raw_timestamp': record.get('date') or '',
            'timestamp': parse_foodpanda_relative_time(record.get('date', '')),
        })
        added += 1
    return added


def _foodpanda_review_card_count(page):
    try:
        if not is_foodpanda_modal_open(page):
            return 0
        return foodpanda_review_modal_locator(page).locator(FOODPANDA_REVIEW_CARDS).count()
    except Exception:
        return 0


def _foodpanda_scroll_reviews_modal(page):
    """Scroll the reviews list inside the modal; tries several container strategies."""
    result = page.evaluate("""() => {
        const cardSelector = '[data-testid="info-reviews-modal-card-container"], [data-testid="info-reviews-modal-review-card"]';
        const modal = document.querySelector('[data-testid="info-reviews-modal-content"]')
            || document.getElementById('info-reviews-content');
        if (!modal) return { scrolled: false, atEnd: true, method: 'no_modal' };

        const cards = [...modal.querySelectorAll(cardSelector)];
        const isScrollable = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const oy = style.overflowY;
            return (oy === 'auto' || oy === 'scroll' || oy === 'overlay')
                && el.scrollHeight > el.clientHeight + 2;
        };
        const findScrollable = (start) => {
            let node = start;
            while (node) {
                if (isScrollable(node)) return node;
                node = node.parentElement;
            }
            return null;
        };

        const candidates = [];
        if (cards.length) candidates.push(findScrollable(cards[cards.length - 1]));
        for (const sel of ['.info-reviews-modal-body', '.bds-c-modal__body', '.bds-c-modal__content-window']) {
            const el = modal.querySelector(sel) || document.querySelector(sel);
            if (el && isScrollable(el)) candidates.push(el);
        }
        candidates.push(findScrollable(modal));

        const scrollable = candidates.find(Boolean) || null;
        let scrolled = false;
        let atEnd = !scrollable;

        if (scrollable) {
            const before = scrollable.scrollTop;
            const max = Math.max(0, scrollable.scrollHeight - scrollable.clientHeight);
            const delta = Math.max(500, scrollable.clientHeight * 0.9);
            scrollable.scrollTop = Math.min(scrollable.scrollTop + delta, max);
            scrolled = scrollable.scrollTop > before;
            atEnd = scrollable.scrollTop >= max - 2;
        }

        if (cards.length && !atEnd) {
            const beforeTop = scrollable ? scrollable.scrollTop : 0;
            cards[cards.length - 1].scrollIntoView({ block: 'end', inline: 'nearest' });
            if (scrollable) {
                const max = Math.max(0, scrollable.scrollHeight - scrollable.clientHeight);
                scrolled = scrolled || scrollable.scrollTop > beforeTop;
                atEnd = scrollable.scrollTop >= max - 2;
            } else {
                scrolled = true;
            }
        }

        return { scrolled, atEnd, method: scrollable ? 'container' : 'scroll_into_view' };
    }""") or {'scrolled': False, 'atEnd': True, 'method': 'evaluate_failed'}

    if not result.get('scrolled'):
        try:
            modal = foodpanda_review_modal_locator(page)
            cards = modal.locator(FOODPANDA_REVIEW_CARDS)
            if cards.count() > 0:
                cards.last.scroll_into_view_if_needed(timeout=FOODPANDA_ACTION_TIMEOUT_MS)
                return {'scrolled': True, 'atEnd': result.get('atEnd', False), 'method': 'playwright'}
        except Exception:
            pass
    return result


def _foodpanda_wait_for_more_reviews(page, before_card_count, before_signature, timeout_ms=None):
    timeout_ms = timeout_ms or FOODPANDA_SCROLL_WAIT_MS
    try:
        page.wait_for_function(
            """([selector, oldCount, oldSig]) => {
                const modal = document.querySelector('[data-testid="info-reviews-modal-content"]')
                    || document.getElementById('info-reviews-content');
                const root = modal || document;
                const nodes = [...root.querySelectorAll(selector)];
                const sig = nodes.map(n => (n.innerText || '').replace(/\\s+/g, ' ').trim())
                    .filter(Boolean).join('\\x1e');
                return nodes.length > oldCount || (sig && sig !== oldSig);
            }""",
            arg=[FOODPANDA_REVIEW_CARDS, before_card_count, before_signature],
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def exhaust_foodpanda_reviews(page, content_obj, seen_ids, shop_id, response_state,
                               dom_stats, max_steps=FOODPANDA_MAX_STEPS):
    stale = 0
    api_cursor = 0
    modal_open = is_foodpanda_modal_open(page)
    last_action = 'none'
    for step in range(max_steps):
        before_count = len(seen_ids)
        before_card_count = _foodpanda_review_card_count(page)
        modal_open = is_foodpanda_modal_open(page)
        harvest_foodpanda_records(
            content_obj, mounted_foodpanda_reviews(page, dom_stats), seen_ids, shop_id,
            source='dom', stats=dom_stats)
        api_records = response_state.get('records', [])[api_cursor:]
        api_cursor += len(api_records)
        harvest_foodpanda_records(
            content_obj, api_records, seen_ids, shop_id, source='api', stats=dom_stats)
        before_signature = foodpanda_dom_signature(page)
        before_api = len(response_state.get('records', []))
        action = 'none'
        scroll_meta = {'scrolled': False, 'atEnd': True, 'method': 'none'}
        modal = foodpanda_review_modal_locator(page) if modal_open else None
        controls = (modal or page).locator("button, [role='button'], a").filter(
            has_text=FOODPANDA_MORE_LABEL_RE)
        for index in range(min(controls.count(), 20)):
            try:
                control = controls.nth(index)
                if control.is_visible():
                    control.click(timeout=FOODPANDA_ACTION_TIMEOUT_MS)
                    action = 'load_more'
                    break
            except Exception:
                continue
        if action == 'none' and modal_open:
            try:
                scroll_meta = _foodpanda_scroll_reviews_modal(page)
                action = 'scroll' if scroll_meta.get('scrolled') else 'none'
            except Exception:
                action = 'none'
        if action != 'none':
            _foodpanda_wait_for_more_reviews(page, before_card_count, before_signature)
            try:
                page.wait_for_timeout(400)
            except Exception:
                pass
        elif scroll_meta.get('atEnd'):
            return {
                'steps': step + 1, 'termination_reason': 'end_of_list',
                'last_action': last_action, 'scroll_method': scroll_meta.get('method'),
            }
        else:
            return {
                'steps': step + 1, 'termination_reason': 'scroll_failed',
                'last_action': last_action, 'scroll_method': scroll_meta.get('method'),
            }
        modal_open = is_foodpanda_modal_open(page)
        harvest_foodpanda_records(
            content_obj, mounted_foodpanda_reviews(page, dom_stats), seen_ids, shop_id,
            source='dom', stats=dom_stats)
        api_records = response_state.get('records', [])[api_cursor:]
        api_cursor += len(api_records)
        harvest_foodpanda_records(
            content_obj, api_records, seen_ids, shop_id, source='api', stats=dom_stats)
        after_card_count = _foodpanda_review_card_count(page)
        progress = (
            len(seen_ids) > before_count
            or len(response_state.get('records', [])) > before_api
            or after_card_count > before_card_count
        )
        stale = 0 if progress else stale + 1
        last_action = action
        if stale >= FOODPANDA_STALE_LIMIT:
            return {
                'steps': step + 1, 'termination_reason': 'no_unique_growth',
                'last_action': action, 'scroll_method': scroll_meta.get('method'),
            }
    return {'steps': max_steps, 'termination_reason': 'safety_limit', 'last_action': last_action}


def derive_foodpanda_entity_name(entity_name, page, shop_url):
    value = normalize_foodpanda_text(entity_name)
    if value:
        return value
    try:
        title = normalize_foodpanda_text(page.title())
        title = re.split(r'\s*[|–—-]\s*(?:foodpanda.*)?$', title, maxsplit=1, flags=re.I)[0]
        title = re.sub(
            r'^(?:ဝေဖန်\s*)?သုံးသပ်ချက်(?:များ)?\s*|^အဆင့်သတ်မှတ်ချက်(?:များ)?\s*',
            '',
            title,
        ).strip()
        if title:
            return title
    except Exception:
        pass
    path_name = unquote(urlparse(shop_url).path.rstrip('/').split('/')[-1]).replace('-', ' ')
    return normalize_foodpanda_text(path_name).title() or 'Foodpanda shop'


def scrape_foodpanda_reviews(page, shop_url, entity_name):
    print(f"\n[INFO] Scraping Foodpanda URL: {shop_url}")
    canonical_shop_url = canonical_foodpanda_shop_url(shop_url)
    shop_uuid = f"fp_shop_{hashlib.sha256(canonical_shop_url.encode('utf-8')).hexdigest()[:16]}"
    response_state = {'records': [], 'matching_responses': 0, 'api_objects': 0,
                      'response_errors': 0, '_record_keys': set()}
    listener = lambda response: collect_foodpanda_review_response(response, response_state)
    page.on('response', listener)
    try:
        page.goto(shop_url, wait_until='domcontentloaded', timeout=FOODPANDA_NAVIGATION_TIMEOUT_MS)
        display_name = derive_foodpanda_entity_name(entity_name, page, shop_url)
        content_obj = get_or_create_content(
            'Platform', display_name, shop_uuid, f'{display_name} Reviews')
        overlay = dismiss_foodpanda_overlays(page)
        surface = open_foodpanda_review_surface(page, response_state, shop_url)
        content_obj['overall_rating'] = extract_foodpanda_overall_rating(page)
        seen_ids = {fb.get('id') or fb.get('source_feedback_id')
                    for fb in content_obj.get('feedbacks', [])}
        dom_stats = {}
        pagination = exhaust_foodpanda_reviews(
            page, content_obj, seen_ids, shop_uuid, response_state, dom_stats)
        diagnostics = {
            'strategy': 'dom-first', 'final_url': normalize_foodpanda_text(page.url),
            'canonical_shop_url': canonical_shop_url,
            'page_title': normalize_foodpanda_text(page.title()), 'overlay': overlay,
            'review_control': surface, 'modal_opened': surface.get('modal_opened', False),
            'matching_responses': response_state['matching_responses'],
            'response_errors': response_state['response_errors'],
            'api_objects': len(response_state['records']),
            'rejected_records': dom_stats.get('rejected_records', 0),
            'overall_rating': content_obj.get('overall_rating'),
            **dom_stats,
            'pagination': pagination, 'reviews_extracted': len(content_obj['feedbacks']),
        }
        if not content_obj['feedbacks']:
            diagnostics['reason'] = ('blocking_overlay_remaining' if overlay['blocker_remaining']
                                     else 'no_review_records_detected')
        content_obj['review_diagnostics'] = diagnostics
        print(f"   -> Extracted {len(content_obj['feedbacks'])} unique reviews. "
              f"({pagination['termination_reason']})")
        return content_obj
    finally:
        try:
            page.remove_listener('response', listener)
        except Exception:
            pass

def scrape_business_blog(page, blog_url, entity_name):
    print(f"\n[INFO] Scraping Blog URL: {blog_url}")
    page.goto(blog_url)
    page.wait_for_timeout(3000)
    article_title = page.title() 
    
    content_obj = get_or_create_content('Web', entity_name, blog_url, article_title)
    paragraphs = page.locator("article p, main p, .content p").all_text_contents()
    
    saved_count = 0
    for text in paragraphs:
        if len(text.strip()) > 20: 
            p_hash = f"blog_para_{hashlib.md5(text.encode('utf-8')).hexdigest()}"
            add_feedback(content_obj, p_hash, text.strip())
            saved_count += 1
    print(f"   -> Extracted {saved_count} paragraphs.")
