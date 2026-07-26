"""
Shared utility functions used by multiple scraping submodules.

Originally part of `scraping.py` — extracted here so `storage`, `lifecycle`,
`facebook`, and `foodpanda` can reuse them without circular imports.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse


# ==========================================
# Timestamp Parsers
# ==========================================

def parse_relative_time(raw_time_str: str, scrape_time: datetime = None) -> str:
    """
    Facebook relative timestamps (e.g. "1d", "12h", "2w", "July 12", "1 July at 14:43")
    ကို Absolute ISO datetime string (YYYY-MM-DD HH:MM:SS) အဖြစ် ပြောင်းပေးသည်။
    
    Returns: ISO format string  e.g.  "2026-07-13 11:11:38"
    """
    if scrape_time is None:
        scrape_time = datetime.now()

    s = raw_time_str.strip().lower()

    # ── Facebook tooltip format: "Tuesday, 1 July 2026 at 14:43" ──
    # Also handles: "1 July 2026 at 14:43", "July 1, 2026 at 2:43 PM"
    tooltip_m = re.search(
        r'(\d{1,2})\s+([a-z]+)\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2})',
        s
    )
    if tooltip_m:
        day = int(tooltip_m.group(1))
        mon_str = tooltip_m.group(2)[:3]
        year = int(tooltip_m.group(3))
        hh = int(tooltip_m.group(4))
        mm_ = int(tooltip_m.group(5))
        months_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        }
        month = months_map.get(mon_str)
        if month:
            try:
                return datetime(year, month, day, hh, mm_).strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass

    # ── US format: "July 1, 2026 at 2:43 PM" ──
    tooltip_us = re.search(
        r'([a-z]+)\s+(\d{1,2}),?\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(am|pm)?',
        s
    )
    if tooltip_us:
        mon_str = tooltip_us.group(1)[:3]
        day = int(tooltip_us.group(2))
        year = int(tooltip_us.group(3))
        hh = int(tooltip_us.group(4))
        mm_ = int(tooltip_us.group(5))
        ampm = tooltip_us.group(6)
        if ampm == 'pm' and hh != 12:
            hh += 12
        elif ampm == 'am' and hh == 12:
            hh = 0
        months_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        }
        month = months_map.get(mon_str)
        if month:
            try:
                return datetime(year, month, day, hh, mm_).strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass

    # ── short notation: "2h", "30m", "5d", "2w", "1y" ──
    m = re.fullmatch(r'(\d+)\s*([mhdwy])', s)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        delta_map = {
            'm': timedelta(minutes=val),
            'h': timedelta(hours=val),
            'd': timedelta(days=val),
            'w': timedelta(weeks=val),
            'y': timedelta(days=val * 365),
        }
        result = scrape_time - delta_map[unit]
        return result.strftime('%Y-%m-%d %H:%M:%S')

    # ── accessible-name notation: "19 hours ago", "2 days ago" ──
    verbose_relative = re.fullmatch(
        r'(\d+)\s+(minute|hour|day|week|year)s?\s+ago', s)
    if verbose_relative:
        value = int(verbose_relative.group(1))
        unit = verbose_relative.group(2)
        delta = {
            'minute': timedelta(minutes=value),
            'hour': timedelta(hours=value),
            'day': timedelta(days=value),
            'week': timedelta(weeks=value),
            'year': timedelta(days=value * 365),
        }[unit]
        return (scrape_time - delta).strftime('%Y-%m-%d %H:%M:%S')

    # ── "just now" / "ယခုတွင်" ──
    if s in ('just now', 'ယခုတွင်', 'now'):
        return scrape_time.strftime('%Y-%m-%d %H:%M:%S')

    # ── "yesterday at HH:MM" / "မနေ့က HH:MM" ──
    m = re.search(r'yesterday.*?(\d{1,2}):(\d{2})', s)
    if m:
        result = (scrape_time - timedelta(days=1)).replace(
            hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        return result.strftime('%Y-%m-%d %H:%M:%S')

    # ── "D Month [at HH:MM]"  e.g.  "1 July at 14:43"  or  "July 1" ──
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        # Myanmar abbreviated months
        'ဇန်': 1, 'ဖေ': 2, 'မတ်': 3, 'ဧ': 4, 'မေ': 5, 'ဇွန်': 6,
        'ဇူ': 7, 'ဩ': 8, 'စက်': 9, 'အောက်': 10, 'နို': 11, 'ဒီ': 12,
    }
    m_date = re.search(r'(\d{1,2})\s+([a-z]{3,}|\w+)(?:\s+at\s+(\d{1,2}):(\d{2}))?', s)
    if m_date:
        day = int(m_date.group(1))
        mon_str = m_date.group(2)[:3]
        month = months.get(mon_str, scrape_time.month)
        year = scrape_time.year
        if month > scrape_time.month:   # past year
            year -= 1
        hh = int(m_date.group(3)) if m_date.group(3) else 0
        mm_ = int(m_date.group(4)) if m_date.group(4) else 0
        try:
            result = datetime(year, month, day, hh, mm_)
            return result.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass

    # ── already absolute (e.g. "2026-07-01 14:43:00") ──
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M'):
        try:
            return datetime.strptime(raw_time_str.strip(), fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass

    # ── fallback: return scrape time ──
    return scrape_time.strftime('%Y-%m-%d %H:%M:%S')


def parse_count(raw):
    """
    Facebook count strings (e.g. '1.2K', '662', '3.5M', '15') ကို integer ပြောင်းပေးသည်။
    """
    if isinstance(raw, int):
        return raw
    if not raw:
        return 0
    s = str(raw).strip().lower().replace(',', '')
    try:
        if s.endswith('k'):
            return int(float(s[:-1]) * 1000)
        elif s.endswith('m'):
            return int(float(s[:-1]) * 1000000)
        else:
            return int(float(s))
    except (ValueError, TypeError):
        return 0




# ==========================================
# MongoDB / general datetime parsing
# ==========================================

def parse_scraped_datetime(value, fallback=None):
    fallback = fallback or datetime.now()
    if isinstance(value, datetime):
        return value
    if not value:
        return fallback
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return fallback



# ==========================================
# UI Text Helpers
# ==========================================

def normalize_ui_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()



# ==========================================
# URL / ID Helpers
# ==========================================

def normalize_source_url(value):
    raw = re.sub(r'\s+', ' ', str(value or '')).strip()
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip('/')
    path = parsed.path.rstrip('/') or '/'
    return urlunparse(parsed._replace(path=path, query='', fragment=''))


def make_scoped_id(prefix, source_url, *parts):
    cleaned_parts = [re.sub(r'\s+', ' ', str(part or '')).strip() for part in parts]
    canonical = '\x1f'.join([normalize_source_url(source_url)] + [
        part for part in cleaned_parts if part
    ])
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"



# ==========================================
# Foodpanda Text Helpers
# ==========================================

def normalize_foodpanda_text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def normalize_foodpanda_rating(value):
    if value is None or isinstance(value, bool):
        return None
    match = re.search(r'([0-5](?:[.,]\d+)?)', str(value))
    if not match:
        return None
    rating = float(match.group(1).replace(',', '.'))
    return int(rating) if rating.is_integer() else rating


def parse_foodpanda_relative_time(raw_time_str, scrape_time=None):
    """
    Foodpanda relative timestamps (e.g. "5 days ago", "1 week ago", "3 months ago")
    ကို absolute ISO datetime string အဖြစ် ပြောင်းပေးသည်။
    """
    if scrape_time is None:
        scrape_time = datetime.now()
    s = (raw_time_str or '').strip().lower()
    if not s:
        return scrape_time.strftime('%Y-%m-%d %H:%M:%S')
    # "just now", "today"
    if s in ('just now', 'today'):
        return scrape_time.strftime('%Y-%m-%d %H:%M:%S')
    # "yesterday"
    if s == 'yesterday':
        return (scrape_time - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    # "a day ago", "a week ago", "an hour ago"
    m = re.match(r'(?:a|an)\s+(minute|hour|day|week|month|year)s?\s+ago', s)
    if m:
        unit = m.group(1)
        delta_map = {
            'minute': timedelta(minutes=1), 'hour': timedelta(hours=1),
            'day': timedelta(days=1), 'week': timedelta(weeks=1),
            'month': timedelta(days=30), 'year': timedelta(days=365),
        }
        return (scrape_time - delta_map.get(unit, timedelta())).strftime('%Y-%m-%d %H:%M:%S')
    # "5 days ago", "2 weeks ago", "3 months ago"
    m = re.match(r'(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago', s)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        delta_map = {
            'minute': timedelta(minutes=val), 'hour': timedelta(hours=val),
            'day': timedelta(days=val), 'week': timedelta(weeks=val),
            'month': timedelta(days=val * 30), 'year': timedelta(days=val * 365),
        }
        return (scrape_time - delta_map.get(unit, timedelta())).strftime('%Y-%m-%d %H:%M:%S')
    # Fallback: try the Facebook-style parser (handles "1d", "2w" short notation)
    return parse_relative_time(raw_time_str, scrape_time)
