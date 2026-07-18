import argparse
import json
import hashlib
from datetime import datetime, timedelta
import os
import time
import random
from urllib.parse import parse_qs, unquote, urlparse, urlunparse
from playwright.sync_api import sync_playwright
import re
from pymongo import MongoClient, UpdateOne

# ==========================================
# 30-Day Lifecycle Tracking Configuration (MongoDB-backed)
# ==========================================
LIFECYCLE_DAYS = 30  # Posts are tracked for this many days before finalization

# MongoDB Configuration — source of truth for dedup/lifecycle state
# (replaces the old tracking_state.json file)
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "feedback_analytics"
CONTENTS_COLLECTION = "contents"
FEEDBACKS_COLLECTION = "feedbacks"

# ==========================================
# အပိုင်း (၀) - Timestamp Parser
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
# အပိုင်း (၁) - In-Memory Data Structure & Storage
# ==========================================
session_data = []

def get_or_create_content(source_type, entity_name, source_content_id, title_or_post):
    for content in session_data:
        if content['source_content_id'] == source_content_id:
            return content
            
    new_content = {
        "source_type": source_type,
        "entity_name": entity_name,
        "source_content_id": source_content_id,
        "title_or_post": title_or_post,
        "feedbacks": []
    }
    session_data.append(new_content)
    return new_content

def add_feedback(content_obj, source_feedback_id, raw_text):
    for fb in content_obj['feedbacks']:
        if fb['source_feedback_id'] == source_feedback_id:
            return 
            
    content_obj['feedbacks'].append({
        "source_feedback_id": source_feedback_id,
        "raw_text": raw_text,
        "feedback_date": datetime.now().isoformat()
    })

def export_to_json(entity_name):
    if not session_data:
        print("[WARNING] No data to save.")
        return
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = entity_name.replace(" ", "_").lower()
    filename = f"raw_{clean_name}_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, ensure_ascii=False, indent=4)
        
    print(f"\n✅ [SUCCESS] Data successfully saved to JSON file: {filename}")

# ==========================================
# အပိုင်း (၁.၅) - 30-Day Lifecycle Tracking (MongoDB-backed)
# ==========================================

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
    return client, client[DB_NAME]


def get_known_posts(db, page_url=None):
    """
    lifecycle_status='tracking' ဖြစ်ပြီး expires_at မကျော်သေးသော posts
    အားလုံးကို {post_id: doc} dict အဖြစ် ပြန်ပေးသည်။
    (page_url ပေးလျှင် ထို page ၏ posts များသာ — မပေးလျှင် အားလုံး၊
     အဟောင်း documents များတွင် page_url field မရှိနိုင်၍ default က အားလုံးဖတ်သည်)
    """
    query = {"lifecycle_status": "tracking", "expires_at": {"$gt": datetime.now()}}
    if page_url:
        query["page_url"] = page_url
    return {doc["_id"]: doc for doc in db[CONTENTS_COLLECTION].find(query)}


def get_final_post_ids(db, page_url=None):
    """
    lifecycle_status='final' ဖြစ်ပြီးသော post _id များကို set အဖြစ် ပြန်ပေးသည်။
    Final posts များကို ထပ်မံ scrape မလုပ်တော့ပါ။
    """
    query = {"lifecycle_status": "final"}
    if page_url:
        query["page_url"] = page_url
    return {doc["_id"] for doc in db[CONTENTS_COLLECTION].find(query, {"_id": 1})}


def finalize_expired_posts_db(db):
    """
    expires_at ကျော်လွန်သွားပြီးသော posts အားလုံးကို
    lifecycle_status='final' သို့ ပြောင်းခြင်း (MongoDB update_many)။

    Returns: finalized post count
    """
    now = datetime.now()
    result = db[CONTENTS_COLLECTION].update_many(
        {"lifecycle_status": "tracking", "expires_at": {"$lte": now}},
        {"$set": {"lifecycle_status": "final", "finalized_at": now}}
    )
    if result.modified_count > 0:
        print(f"\n[LIFECYCLE] {result.modified_count} post(s) archived as 'final' "
              f"(past {LIFECYCLE_DAYS}-day window).")
    return result.modified_count


def show_tracking_status_db(db):
    """
    MongoDB ရှိ tracking state summary ကို ပြသခြင်း —
    tracking/final counts နှင့် recently-updated posts များ။
    """
    contents_col = db[CONTENTS_COLLECTION]
    tracking_count = contents_col.count_documents({"lifecycle_status": "tracking"})
    final_count = contents_col.count_documents({"lifecycle_status": "final"})
    total_count = contents_col.count_documents({})

    print(f"\n{'='*60}")
    print(f"📊 {LIFECYCLE_DAYS}-Day Lifecycle Tracking Status (MongoDB)")
    print(f"{'='*60}")
    print(f"   🔄 Actively Tracking: {tracking_count} posts")
    print(f"   📦 Finalized (Done):  {final_count} posts")
    print(f"   📋 Total Tracked:     {total_count} posts")

    if total_count == 0:
        print("\n[INFO] No posts are being tracked yet. Run a Facebook scrape first.")
        return

    now = datetime.now()
    recent = contents_col.find().sort("last_updated_at", -1).limit(10)
    print(f"\n   {'─'*56}")
    print(f"   🕒 RECENTLY UPDATED POSTS (latest 10):")
    print(f"   {'─'*56}")
    for doc in recent:
        preview = str(doc.get("title_or_post") or doc.get("post_text_preview") or doc["_id"])[:45]
        status = doc.get("lifecycle_status", "?")
        scrapes = doc.get("scrape_count", 1)
        expires_at = doc.get("expires_at")
        if status == "tracking" and isinstance(expires_at, datetime):
            days_left = max(0, (expires_at - now).days)
            extra = f"Days left: {days_left}"
        else:
            extra = "archived"
        history = doc.get("engagement_history", [])
        latest_reactions = history[-1].get("reactions", 0) if history else doc.get("total_reactions", 0)
        print(f"   • [{status}] {preview}...")
        print(f"     Scrapes: {scrapes} | {extra} | {latest_reactions} reactions")

    print(f"\n{'='*60}")


# ==========================================
# အပိုင်း (၂) - Facebook Authentication Logic
# ==========================================
def load_cookies(context, cookie_file="cookies.json"):
    """
    JSON ဖိုင်မှ Cookies များကို ဖတ်ပြီး Playwright နားလည်သော Format သို့ 
    အလိုအလျောက် ပြောင်းလဲကာ Browser ထဲသို့ ထည့်သွင်းခြင်း
    """
    if os.path.exists(cookie_file):
        print(f"\n[INFO] Loading Facebook cookies from '{cookie_file}'...")
        with open(cookie_file, 'r', encoding='utf-8') as f:
            raw_cookies = json.load(f)
            
        playwright_cookies = []
        for cookie in raw_cookies:
            p_cookie = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie["path"],
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False)
            }
            
            if "expirationDate" in cookie:
                p_cookie["expires"] = cookie["expirationDate"]
                
            same_site = cookie.get("sameSite", "Lax").lower()
            if same_site == "no_restriction":
                p_cookie["sameSite"] = "None"
            elif same_site == "unspecified":
                p_cookie["sameSite"] = "Lax"
            else:
                p_cookie["sameSite"] = same_site.capitalize()
                
            playwright_cookies.append(p_cookie)
            
        context.add_cookies(playwright_cookies)
        print("[SUCCESS] Cookies format converted and injected successfully! You are logged in.")
    else:
        print(f"\n[WARNING] '{cookie_file}' not found. Proceeding as a Guest (No Login).")

# ==========================================
# အပိုင်း (၃) - Comment Timestamp Extractor
# ==========================================

def extract_comment_timestamp(article_element, scrape_time: datetime) -> str:
    """
    Comment article element မှ relative timestamp ကို ဖတ်ပြီး
    absolute datetime string ပြောင်းပေးသည်။
    
    Facebook မှ timestamp များ:  <a aria-label="...">  or  abbr[title]  or plain text
    e.g. "1d", "12h", "July 12 at 10:00 AM", "1 July at 14:43"
    """
    # Strategy 1: <a> tags whose text matches time pattern
    try:
        time_links = article_element.locator("a").all()
        for link in time_links:
            txt = (link.inner_text() or "").strip()
            # Match short notations: 1d, 2h, 30m, 3w, 1y
            if re.fullmatch(r'\d+[mhdwy]', txt, re.IGNORECASE):
                return parse_relative_time(txt, scrape_time)
            # Match "July 12", "1 July", etc.
            if re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}\s+\w+)', txt, re.IGNORECASE):
                return parse_relative_time(txt, scrape_time)
            # Match aria-label on link
            aria = link.get_attribute("aria-label") or ""
            if aria:
                return parse_relative_time(aria, scrape_time)
    except Exception:
        pass

    # Strategy 2: abbr[title] tag
    try:
        abbr = article_element.locator("abbr[title]").first
        if abbr.count() > 0:
            title_val = abbr.get_attribute("title") or ""
            if title_val:
                return parse_relative_time(title_val, scrape_time)
    except Exception:
        pass

    # Strategy 3: Scan all text nodes for time-like patterns
    try:
        raw = article_element.inner_text()
        # Look for short time tokens in the raw text
        tokens = re.findall(r'\b\d+[mhdwy]\b', raw, re.IGNORECASE)
        if tokens:
            return parse_relative_time(tokens[0], scrape_time)
    except Exception:
        pass

    return scrape_time.strftime('%Y-%m-%d %H:%M:%S')


# ==========================================
# အပိုင်း (၃.၅) - Post Engagement Metrics Extractor
# ==========================================

def extract_engagement_metrics(post_locator):
    """
    Post locator တစ်ခုမှ engagement metrics (reactions, shares, comments)
    ကို ထုတ်ယူပြီး (reactions, shares, comments) integer tuple ပြန်ပေးသည်။
    New-post full scrape နှင့် known-post engagement refresh နှစ်ခုလုံးက သုံးသည်။
    """
    total_reactions = 0
    total_shares = 0
    total_comments = 0
    try:
        metrics = post_locator.evaluate("""(node) => {
            const result = {reactions: 0, shares: 0, comments: 0};
            // Find all text spans in the post's action bar area
            const allSpans = Array.from(node.querySelectorAll('span'));
            for (const span of allSpans) {
                const t = span.textContent.trim().toLowerCase();
                // "662" or "1.2K" near reaction toolbar (aria-label often has count)
                // "16 comments" or "265 shares"
                const commMatch = t.match(/^(\\d[\\d,.]*k?)\\s*(comments?|မှတ်ချက်)/);
                const shareMatch = t.match(/^(\\d[\\d,.]*k?)\\s*(shares?|ဝေမျှမှု)/);
                if (commMatch) result.comments = commMatch[1];
                if (shareMatch) result.shares = shareMatch[1];
            }
            // Reaction count: look for aria-label on the reaction toolbar button
            const reactionBtns = Array.from(node.querySelectorAll('[aria-label]'));
            for (const btn of reactionBtns) {
                const label = btn.getAttribute('aria-label') || '';
                // e.g. "662 people reacted" or "662"
                const rMatch = label.match(/(\\d[\\d,.]*k?)\\s*(people|others|you and|total|reactions?|person)/i);
                if (rMatch) { result.reactions = rMatch[1]; break; }
            }
            return result;
        }""")
        total_reactions = parse_count(metrics.get('reactions', 0))
        total_shares = parse_count(metrics.get('shares', 0))
        total_comments = parse_count(metrics.get('comments', 0))
    except Exception:
        pass
    return total_reactions, total_shares, total_comments


# ==========================================
# အပိုင်း (၃.၆) - Comment Filter & Pagination Helpers
# ==========================================

ALL_COMMENTS_LABELS = ('all comments', 'မှတ်ချက်အားလုံး', 'အားလုံး')
COMMENT_SORT_LABELS = ALL_COMMENTS_LABELS + (
    'most relevant', 'newest', 'top comments',
    'ဆီလျော်မှုအရှိဆုံး', 'အသစ်ဆုံး',
)
DIRECT_COMMENT_RE = re.compile(
    r'(?:view|see)\s+(?:(?:\d+\s+)?(?:more|previous)\s+comments?|'
    r'\d+\s+(?:more\s+)?comments?|all\s+\d+\s+comments?)|'
    r'မှတ်ချက်များ\s*ထပ်မံ|ယခင်မှတ်ချက်', re.IGNORECASE)
REPLY_CONTROL_RE = re.compile(
    r'(?:view|see)\s+\d*\s*(?:more\s+)?repl(?:y|ies)|'
    r'\d+\s+repl(?:y|ies)|ပြန်ကြားချက်', re.IGNORECASE)


def normalize_ui_text(value):
    """Normalize Facebook UI text without changing meaningful Unicode content."""
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def expand_mounted_comment_text(target_container):
    """Expand only See-more controls that belong to a mounted comment article."""
    try:
        return int(target_container.evaluate("""(root) => {
            let clicked = 0;
            for (const article of root.querySelectorAll("div[role='article']")) {
                for (const el of article.querySelectorAll("div[role='button'], span[role='button'], a[role='button']")) {
                    const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                    if (/^(see more|ပိုမိုကြည့်ရှုရန်)$/i.test(t)) { el.click(); clicked++; }
                }
            }
            return clicked;
        }""") or 0)
    except Exception:
        return 0


def classify_comment_depth(article):
    """Return 0 for direct, >0 for reply, or None when structure is ambiguous."""
    try:
        return article.evaluate("""(node) => {
            // 1. Explicit depth metadata is the strongest signal.
            const rawDepth = node.getAttribute('data-comment-depth') ||
                             node.getAttribute('data-depth');
            if (rawDepth !== null && rawDepth !== '' && !Number.isNaN(Number(rawDepth))) {
                return Number(rawDepth);
            }
            // 2. Permalinks distinguish reply IDs from direct comment IDs.
            const hrefs = Array.from(node.querySelectorAll('a[href]'))
                .map(a => decodeURIComponent(a.href || a.getAttribute('href') || ''));
            if (hrefs.some(href => /(?:[?&]|^)reply_comment_id=/i.test(href))) return 1;
            if (hrefs.some(href => /(?:[?&]|^)comment_id=/i.test(href))) return 0;
            // 3. A nearest enclosing comment article means this article is nested.
            const parentArticle = node.parentElement &&
                node.parentElement.closest("div[role='article']");
            if (parentArticle) {
                const parentLooksLikeComment = parentArticle.hasAttribute('data-commentid') ||
                    parentArticle.hasAttribute('data-comment-id') ||
                    Array.from(parentArticle.querySelectorAll('a[href]')).some(a =>
                        /(?:comment_id|reply_comment_id)(?:=|%3D)/i.test(a.href || ''));
                if (parentLooksLikeComment) return 1;
            }
            // 4. Explicit aria semantics are fallback evidence only.
            const label = (node.getAttribute('aria-label') || '').toLocaleLowerCase();
            if (/reply|ပြန်လည်ဖြေကြားချက်|ပြန်ကြားချက်/.test(label)) return 1;
            if (/comment by|comment from|မှတ်ချက်ရေးသားသူ/.test(label)) return 0;
            // 5. Indentation is layout-dependent and therefore last-resort evidence.
            const rect = node.getBoundingClientRect();
            const parentRect = node.parentElement && node.parentElement.getBoundingClientRect();
            if (parentRect && rect.left - parentRect.left > 24) return 1;
            return null;
        }""")
    except Exception:
        return None


def extract_facebook_comment_id(article):
    """Return a direct comment ID from an attribute or decoded permalink."""
    data = article.evaluate("""(node) => ({
        attributeId: node.getAttribute('data-commentid') ||
                     node.getAttribute('data-comment-id') || '',
        hrefs: Array.from(node.querySelectorAll('a[href]')).map(a => a.getAttribute('href') || '')
    })""") or {}
    attribute_id = normalize_ui_text(data.get('attributeId'))
    if attribute_id:
        return attribute_id
    for raw_href in data.get('hrefs') or []:
        decoded = unquote(str(raw_href))
        for candidate in (decoded, unquote(decoded)):
            query = parse_qs(urlparse(candidate).query)
            # A reply permalink can carry both IDs; never identify it as direct.
            if query.get('reply_comment_id'):
                continue
            comment_ids = query.get('comment_id') or query.get('comment_id[]')
            if comment_ids and str(comment_ids[0]).isdigit():
                return str(comment_ids[0])
            match = re.search(r'(?:[?&]|^)comment_id=(\d+)(?:&|$)', candidate, re.IGNORECASE)
            if match and not re.search(r'(?:[?&]|^)reply_comment_id=', candidate, re.IGNORECASE):
                return match.group(1)
    return ''


def build_comment_identity(post_id, stable_id, author, raw_timestamp, text, attachment_identity=''):
    if stable_id:
        return f"fb_comm_{stable_id}"
    parts = [post_id, normalize_ui_text(author), normalize_ui_text(raw_timestamp),
             normalize_ui_text(text), normalize_ui_text(attachment_identity)]
    return 'fb_comm_' + hashlib.sha256('\x1f'.join(parts).encode('utf-8')).hexdigest()


def open_comment_container(page, post, post_text):
    """Open and identify this post's full comment container without using global `.first`."""
    result = {'container': post, 'dialog': None, 'dialog_valid': False,
              'reason': 'comments_counter_not_found'}
    try:
        # Capture the visible-dialog count so a pre-existing unrelated modal is
        # never automatically selected merely because it is first in the DOM.
        dialogs = page.locator("div[role='dialog']")
        visible_before = sum(1 for i in range(dialogs.count()) if dialogs.nth(i).is_visible())
        clicked = bool(post.evaluate("""(node) => {
            const els = Array.from(node.querySelectorAll('[role="button"], a, span'));
            const el = els.find(x => {
                const t = (x.textContent || '').replace(/\\s+/g, ' ').trim();
                return /^(?:[\\d,.]+[kKmM]?\\s*)?(?:comments?|မှတ်ချက်)/i.test(t) && t.length < 50;
            });
            if (!el) return false; el.click(); return true;
        }"""))
        if not clicked:
            return result
        page.wait_for_timeout(2500)
        dialogs = page.locator("div[role='dialog']")
        candidates = []
        needle = normalize_ui_text(post_text)[:80].lower()
        for i in range(dialogs.count()):
            dialog = dialogs.nth(i)
            try:
                if not dialog.is_visible():
                    continue
                text = normalize_ui_text(dialog.inner_text()).lower()
                articles = dialog.locator("div[role='article']").count()
                has_comment_ui = bool(re.search(r'comment|reply|မှတ်ချက်|ပြန်ကြား', text))
                correlated = bool(needle and needle[:30] in text)
                if articles or has_comment_ui:
                    is_new = i >= visible_before
                    candidates.append((correlated, is_new, articles, dialog))
            except Exception:
                continue
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
            chosen = candidates[0][3]
            return {'container': chosen, 'dialog': chosen, 'dialog_valid': True,
                    'reason': 'validated_comment_dialog'}
        result['reason'] = 'no_valid_comment_dialog'
    except Exception as exc:
        result['reason'] = f'dialog_error:{type(exc).__name__}'
    return result


def close_comment_dialog(page, dialog):
    if dialog is None:
        return
    try:
        if dialog.is_visible():
            close = dialog.locator("[aria-label='Close'], [aria-label='ပိတ်ရန်']")
            if close.count() and close.first.is_visible():
                close.first.click()
            else:
                page.keyboard.press('Escape')
            page.wait_for_timeout(500)
    except Exception:
        pass


def _normalized_label(value):
    return normalize_ui_text(value).casefold()


def comment_dom_signature(target_container):
    """Describe the currently mounted comment window without assuming it is complete."""
    try:
        values = target_container.evaluate("""(root) => Array.from(
            root.querySelectorAll("div[role='article']")
        ).map((node) => {
            const id = node.getAttribute('data-commentid') ||
                       node.getAttribute('data-comment-id') || '';
            const href = Array.from(node.querySelectorAll('a[href]'))
                .map(a => a.href || a.getAttribute('href') || '')
                .find(h => /(?:comment_id|reply_comment_id)(?:=|%3D)/i.test(h)) || '';
            const text = (node.innerText || node.textContent || '')
                .replace(/\\s+/g, ' ').trim().slice(0, 240);
            return id || href || text;
        }).filter(Boolean)""") or []
    except Exception:
        values = []
    canonical = '\x1e'.join(normalize_ui_text(value) for value in values)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest() if canonical else ''


def _comment_loading_state(target_container):
    """Return loading state scoped to the validated comment surface."""
    try:
        return target_container.evaluate("""(root) => {
            const visible = (el) => {
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                       rect.width > 0 && rect.height > 0;
            };
            const busy = root.getAttribute('aria-busy') === 'true' ||
                Array.from(root.querySelectorAll('[aria-busy="true"]')).some(visible);
            const spinner = Array.from(root.querySelectorAll(
                '[role="progressbar"], [aria-label*="Loading" i], [aria-label*="တင်နေ" i]'
            )).some(visible);
            return {busy, spinner};
        }""") or {'busy': False, 'spinner': False}
    except Exception:
        return {'busy': False, 'spinner': False}


def _has_direct_comment_control(target_container):
    try:
        texts = target_container.locator(
            "div[role='button'], span[role='button'], a[role='button'], button"
        ).all_text_contents()
        return any(DIRECT_COMMENT_RE.search(normalize_ui_text(text)) and
                   not REPLY_CONTROL_RE.search(normalize_ui_text(text)) for text in texts)
    except Exception:
        return False


def wait_for_comments_ready(target_container, previous_signature=None, timeout_ms=12000,
                            poll_ms=100):
    """Wait for scoped loading to clear and observable comment state to settle."""
    started = time.monotonic()
    deadline = started + max(timeout_ms, 0) / 1000
    saw_loading = False
    stable_since = None
    last_signature = comment_dom_signature(target_container)
    while time.monotonic() < deadline:
        state = _comment_loading_state(target_container)
        loading = bool(state.get('busy') or state.get('spinner'))
        saw_loading = saw_loading or loading
        signature = comment_dom_signature(target_container)
        changed = previous_signature is not None and signature != previous_signature
        if not loading:
            if changed:
                return {'ready': True, 'changed': True, 'reason': 'signature_changed',
                        'elapsed_ms': int((time.monotonic() - started) * 1000)}
            if stable_since is None or signature != last_signature:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= 0.35:
                reason = ('loading_cleared' if saw_loading else
                          ('control_exhausted' if not _has_direct_comment_control(target_container)
                           else 'stable'))
                return {'ready': True, 'changed': False, 'reason': reason,
                        'elapsed_ms': int((time.monotonic() - started) * 1000)}
        else:
            stable_since = None
        last_signature = signature
        target_container.page.wait_for_timeout(poll_ms)
    return {'ready': False, 'changed': False, 'reason': 'timeout',
            'elapsed_ms': int((time.monotonic() - started) * 1000)}


def wait_for_comment_settle(target_container, page=None, previous_signature=None,
                            timeout=12000):
    """Compatibility wrapper for scoped readiness synchronization."""
    return wait_for_comments_ready(target_container, previous_signature, timeout)


def _read_active_comment_sort(target_container):
    known = {_normalized_label(label) for label in COMMENT_SORT_LABELS}
    try:
        values = target_container.evaluate("""(root) => Array.from(
            root.querySelectorAll('[role="button"], [aria-haspopup], [aria-checked="true"]')
        ).flatMap(el => [el.innerText || el.textContent || '', el.getAttribute('aria-label') || ''])""") or []
    except Exception:
        return ''
    for value in values:
        label = normalize_ui_text(value)
        if _normalized_label(label) in known:
            return label
    return ''


def _exact_label_from_locator(locator, labels):
    text = normalize_ui_text(locator.inner_text() or '')
    aria = normalize_ui_text(locator.get_attribute('aria-label') or '')
    for value in (text, aria):
        normalized = _normalized_label(value)
        if normalized in labels:
            return value
        # Menu decorations such as a checkmark must not alter the semantic first line.
        first_line = _normalized_label(value.split('\n', 1)[0])
        if first_line in labels:
            return value.split('\n', 1)[0]
    return ''


def switch_to_all_comments(target_container, page, max_attempts=4):
    """Select and verify exact All Comments in the validated comment surface."""
    all_labels = {_normalized_label(label) for label in ALL_COMMENTS_LABELS}
    sort_labels = {_normalized_label(label) for label in COMMENT_SORT_LABELS}
    result = {'confirmed': False, 'reason': 'sort_control_not_found', 'attempts': 0,
              'active_label': _read_active_comment_sort(target_container),
              'settle_timeouts': 0}
    for attempt in range(max_attempts):
        active = _read_active_comment_sort(target_container)
        result['active_label'] = active
        if _normalized_label(active) in all_labels:
            result.update(confirmed=True, reason='all_comments_confirmed')
            return result
        result['attempts'] = attempt + 1
        controls = target_container.locator(
            '[aria-haspopup="menu"], [aria-haspopup="listbox"], [role="button"]'
        )
        control = None
        for index in range(controls.count()):
            item = controls.nth(index)
            try:
                if item.is_visible() and _exact_label_from_locator(item, sort_labels):
                    control = item
                    break
            except Exception:
                continue
        if control is None:
            result['reason'] = 'sort_control_not_found'
            continue
        before = comment_dom_signature(target_container)
        try:
            control.click(timeout=3000)
            popup = page.locator('[role="menu"]:visible, [role="listbox"]:visible').last
            popup.wait_for(state='visible', timeout=3000)
        except Exception as exc:
            result['reason'] = f'sort_menu_error:{type(exc).__name__}'
            continue
        option = None
        items = popup.locator('[role="menuitem"], [role="menuitemradio"], [role="option"]')
        for index in range(items.count()):
            item = items.nth(index)
            try:
                if item.is_visible() and _exact_label_from_locator(item, all_labels):
                    option = item
                    break
            except Exception:
                continue
        if option is None:
            page.keyboard.press('Escape')
            result['reason'] = 'all_comments_option_not_found'
            continue
        try:
            option.click(timeout=3000)
        except Exception as exc:
            result['reason'] = f'all_comments_click_error:{type(exc).__name__}'
            continue
        settled = wait_for_comment_settle(target_container, page, before, timeout=12000)
        if not settled['ready']:
            result['settle_timeouts'] += 1
        active = _read_active_comment_sort(target_container)
        result['active_label'] = active
        if _normalized_label(active) in all_labels:
            result.update(confirmed=True, reason='all_comments_confirmed')
            return result
        result['reason'] = 'all_comments_not_confirmed'
    return result

def exhaust_view_more_comments(target_container, page, dialog_opened, post_locator=None, harvest_cb=None):
    """
    "View more comments" / "See previous comments" buttons များကို
    recursive click လုပ်ပြီး direct comments အားလုံးကို DOM ထဲ load ခြင်း။

    Features:
      • Broad text matching (English + Myanmar variants)
      • Reply thread exclusion ("View X replies" ကို ရှောင်)
      • Anti-bot randomized delays (1.5–3.5s normal, 4–6s every 5th click)
      • Stale-count bail-out (8 consecutive no-growth → exit)
      • Max 300 iterations safety cap
      • Incremental harvesting (harvest_cb) to defeat DOM virtualization

    harvest_cb: optional callable invoked after each scroll/click iteration to
                capture the currently-mounted comment articles BEFORE Facebook's
                virtualized list unmounts off-screen (older) comments. This is
                the core fix for "only newest direct comments extracted".
    """
    MAX_ITERATIONS = 300  # posts with hundreds of comments load in small batches
    STALE_LIMIT = 8       # was 4 — virtualized lists often show flat article counts

    # ── Harvest whatever is ALREADY mounted BEFORE any scrolling happens ──
    # (Fix #2) Without this, Step 1's very first scroll-to-bottom could evict
    # the initial render's comments before anything is ever saved.
    if harvest_cb is not None:
        try:
            harvest_cb()
        except Exception:
            pass

    # ── Step 1: Initial scroll to trigger lazy-loading ──
    if dialog_opened:
        for _ in range(5):
            try:
                target_container.evaluate("(node) => { node.scrollTop = node.scrollHeight; }")
            except Exception:
                pass
            page.wait_for_timeout(int(random.uniform(1000, 1800)))
            # (Fix #2) Harvest immediately after each incremental scroll step —
            # older comments revealed by this step must be captured now, before
            # the NEXT scroll step can unmount them from the virtualized DOM.
            if harvest_cb is not None:
                try:
                    harvest_cb()
                except Exception:
                    pass
    else:
        for _ in range(3):
            try:
                if post_locator:
                    post_locator.scroll_into_view_if_needed(timeout=2000)
                page.keyboard.press("End")
            except Exception:
                pass
            page.wait_for_timeout(int(random.uniform(1000, 1800)))
            # (Fix #2) Same rationale as above for the no-dialog fallback path.
            if harvest_cb is not None:
                try:
                    harvest_cb()
                except Exception:
                    pass

    # ── Step 2: Pagination loop ──
    # Regex for "View more comments" variants — EXCLUDES reply threads
    # Matches Facebook's "load more direct comments" buttons with flexible
    # whitespace, e.g.:
    #   "View more comments", "See more comments",
    #   "View 30 more comments", "See 12 more comments",
    #   "View previous comments", "See previous comments",
    #   "View all 304 comments"
    # while still EXCLUDING reply-thread buttons (guarded by REPLY_RE below).
    VIEW_MORE_RE = re.compile(
        r'(?:view|see)\s+'
        r'(?:'
        r'(?:\d+\s+)?more\s+comment'          # "more comments" / "30 more comments"
        r'|(?:\d+\s+)?previous\s+comment'     # "previous comments" / "12 previous comments"
        r'|\d+\s+(?:more\s+)?comment'         # "30 comments" / "30 more comments"
        r'|all\s+\d+\s+comment'               # "all 304 comments"
        r'|more\s+comment'                    # bare "more comments"
        r'|previous\s+comment'                # bare "previous comments"
        r')'
        r'|မှတ်ချက်များ\s*ထပ်မံ'
        r'|ယခင်မှတ်ချက်',
        re.IGNORECASE
    )
    # Regex to REJECT reply-thread buttons
    REPLY_RE = re.compile(
        r'(?:view|see)\s+\d*\s*(?:more\s+)?repl(?:y|ies)'
        r'|ပြန်ကြားချက်'
        r'|\d+\s+repl(?:y|ies)',
        re.IGNORECASE
    )

    prev_article_count = 0
    stale_streak = 0

    for iteration in range(MAX_ITERATIONS):
        # Count current articles to detect stale clicks
        try:
            current_count = target_container.locator("div[role='article']").count()
        except Exception:
            current_count = prev_article_count

        # ── Strategy A: Playwright text-based locator ──
        clicked = False
        try:
            candidates = target_container.get_by_text(VIEW_MORE_RE).all()
            for candidate in candidates:
                try:
                    candidate_text = candidate.inner_text(timeout=1000).strip()
                    # ISOLATION: Skip if this is a reply-thread button
                    if REPLY_RE.search(candidate_text):
                        continue
                    if candidate.is_visible(timeout=1500):
                        candidate.scroll_into_view_if_needed(timeout=2000)
                        page.wait_for_timeout(int(random.uniform(300, 600)))
                        candidate.click(timeout=3000)
                        clicked = True
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # ── Strategy B: JS fallback with tighter element targeting ──
        if not clicked:
            try:
                clicked = target_container.evaluate("""(node) => {
                    // Target only interactive elements — NOT every '*' in the DOM
                    const els = Array.from(node.querySelectorAll(
                        "div[role='button'], span[role='button'], a[role='button'], " +
                        "span[dir='auto'], a, span"
                    ));
                    const replyRe = /(?:view|see)\\s+\\d*\\s*(?:more\\s+)?repl(?:y|ies)|\\d+\\s+repl(?:y|ies)|ပြန်ကြားချက်/i;
                    const viewMoreRe = /^(?:(?:view|see)\\s+(?:more\\s+comment|previous\\s+comment|\\d+\\s+(?:more\\s+)?comment|all\\s+\\d+\\s+comment)|မှတ်ချက်များ\\s*ထပ်မံ|ယခင်မှတ်ချက်)/i;

                    const btn = els.find(el => {
                        const t = el.textContent.trim();
                        if (t.length > 60) return false;
                        if (replyRe.test(t)) return false;  // ISOLATION: skip replies
                        return viewMoreRe.test(t);
                    });
                    if (btn) {
                        btn.scrollIntoView({block: 'center'});
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
            except Exception:
                clicked = False

        if not clicked:
            print(f"        [PAGINATION] No more 'View more comments' found after {iteration} clicks.")
            break

        # ── Anti-bot throttling: randomized delay ──
        if (iteration + 1) % 5 == 0:
            # Every 5th click: longer pause to mimic human browsing
            delay = random.uniform(4.0, 6.0)
            print(f"        [PAGINATION] Click {iteration + 1} — extended pause ({delay:.1f}s)...")
        else:
            delay = random.uniform(1.5, 3.5)
        page.wait_for_timeout(int(delay * 1000))

        # ── Incremental harvest (Fix #2 — timing is critical): capture the
        #    batch of comments that was JUST revealed by the "View more
        #    comments" click IMMEDIATELY, while it is still mounted, and
        #    BEFORE the scroll-to-bottom below runs. Facebook virtualizes the
        #    comment list and unmounts off-screen (older) articles once the
        #    container scrolls past them, so harvesting only AFTER the scroll
        #    (the old behavior) could lose the very comments this click just
        #    loaded. Harvesting here first — before any further scrolling —
        #    is what guarantees ALL direct comments are collected, not just
        #    the last visible (newest) window. ──
        if harvest_cb is not None:
            try:
                harvest_cb()
            except Exception:
                pass

        # ── Scroll after click to trigger lazy-loading of the NEXT batch ──
        if dialog_opened:
            try:
                target_container.evaluate("(node) => { node.scrollTop = node.scrollHeight; }")
            except Exception:
                pass
            page.wait_for_timeout(int(random.uniform(800, 1200)))

        # ── Settle wait: give slow/lazy-loaded (or virtualized) comment
        #    batches time to render before we compare counts, so a slow batch
        #    is not misread as "done". ──
        page.wait_for_timeout(int(random.uniform(2500, 3000)))

        # ── Stale-count detection ──
        try:
            new_count = target_container.locator("div[role='article']").count()
        except Exception:
            new_count = current_count

        # ── Safety-net harvest: after the post-scroll settle, capture
        #    anything newly rendered during the settle wait too. This is a
        #    cheap, idempotent (seen_ids-deduped) extra pass — the critical
        #    pre-scroll harvest above is what actually prevents comment loss. ──
        if harvest_cb is not None:
            try:
                harvest_cb()
            except Exception:
                pass

        if new_count <= prev_article_count:
            stale_streak += 1
            if stale_streak >= STALE_LIMIT:
                print(f"        [PAGINATION] Comment count unchanged for {stale_streak} clicks — "
                      f"stopping ({new_count} articles).")
                break
        else:
            stale_streak = 0
        prev_article_count = new_count

    # ── Step 3: Expand truncated comment text ("See more" inside comments) ──
    try:
        target_container.evaluate("""(node) => {
            node.querySelectorAll("div[role='button'], span[dir='auto']").forEach(b => {
                const t = b.innerText || '';
                if (/^see more$|^ပိုမိုကြည့်ရှုရန်$/i.test(t.trim())) b.click();
            });
        }""")
    except Exception:
        pass
    page.wait_for_timeout(1000)

    print(f"        [PAGINATION] Done. ~{prev_article_count} article elements loaded in DOM.")


# ==========================================
# အပိုင်း (၃.၇) - Direct-comment harvester (virtualization-safe)
# ==========================================

def harvest_comments(target_container, post_id, scrape_time, seen_ids, content_obj,
                     stats):
    """Harvest the currently mounted, structurally confirmed direct comments."""
    stats.setdefault('unknown_depth', 0)
    expand_mounted_comment_text(target_container)
    articles = target_container.locator("div[role='article']").all()
    added = 0
    for article in articles:
        depth = classify_comment_depth(article)
        if depth is None:
            stats['unknown_depth'] += 1
            continue
        if depth > 0:
            continue
        payload = article.evaluate("""(node) => {
            const clone = node.cloneNode(true);
            clone.querySelectorAll("div[role='article'] div[role='article']").forEach(n => n.remove());
            const links = Array.from(clone.querySelectorAll('a'));
            const authorLink = links.find(a => {
                const t = (a.textContent || '').trim();
                return t && !/^\\d+[mhdwy]$/i.test(t) && !/like|reply|share/i.test(t);
            });
            const selectors = ['[data-ad-preview="message"]',
                '[data-ad-comet-preview="message"]', '[dir="auto"][style*="text-align"]'];
            let message = '';
            for (const selector of selectors) {
                const found = Array.from(clone.querySelectorAll(selector)).find(el => {
                    const t = (el.textContent || '').trim();
                    return t && (!authorLink || t !== authorLink.textContent.trim());
                });
                if (found) { message = found.textContent.trim(); break; }
            }
            const media = Array.from(clone.querySelectorAll('img, video, [role="img"]')).map(el => ({
                type: el.tagName.toLowerCase() === 'video' ? 'video' :
                      (/gif/i.test(el.getAttribute('alt') || '') ? 'gif' : 'image'),
                alt: el.getAttribute('alt') || el.getAttribute('aria-label') || '',
                src: el.getAttribute('src') || ''
            })).filter(x => x.alt || x.src);
            return {author: authorLink ? authorLink.textContent.trim() : '', message, media};
        }""") or {}
        author = normalize_ui_text(payload.get('author')) or 'Unknown'
        message = normalize_ui_text(payload.get('message'))
        attachments = payload.get('media') or []
        if not message and not attachments:
            continue
        attachment_identity = json.dumps(attachments, sort_keys=True, ensure_ascii=False)
        raw_timestamp = extract_comment_raw_timestamp(article)
        timestamp = (parse_relative_time(raw_timestamp, scrape_time) if raw_timestamp
                     else scrape_time.strftime('%Y-%m-%d %H:%M:%S'))
        stable_id = extract_facebook_comment_id(article)
        feedback_id = build_comment_identity(
            post_id, stable_id, author, raw_timestamp, message, attachment_identity)
        if feedback_id in seen_ids:
            continue
        seen_ids.add(feedback_id)
        content_obj['feedbacks'].append({
            'id': feedback_id, 'facebook_comment_id': stable_id or None,
            'author': author, 'text': message or f"[{attachments[0]['type']} attachment]",
            'raw_timestamp': raw_timestamp, 'timestamp': timestamp,
            'likes': extract_comment_reactions(article), 'attachments': attachments,
        })
        added += 1
    return added


def extract_comment_raw_timestamp(article):
    try:
        for link in article.locator('a').all():
            text = normalize_ui_text(link.inner_text())
            aria = normalize_ui_text(link.get_attribute('aria-label'))
            if re.fullmatch(r'\d+[mhdwy]', text, re.IGNORECASE):
                return aria or text
            if aria and re.search(r'\d', aria):
                return aria
    except Exception:
        pass
    return ''


def extract_comment_reactions(article):
    try:
        return parse_count(article.evaluate("""(node) => {
            for (const el of node.querySelectorAll('[aria-label]')) {
                const m = (el.getAttribute('aria-label') || '').match(/([\\d,.]+[kKmM]?)\\s*(?:reactions?|likes?|people|person)/i);
                if (m) return m[1];
            }
            return 0;
        }""") or 0)
    except (ValueError, TypeError):
        return 0
    except Exception:
        return 0


# ==========================================
# အပိုင်း (၄) - Dynamic Scrapers
# ==========================================

def scrape_facebook_page_feed(page, page_url, entity_name, max_posts, db, output_filename="facebook_data.json"):
    """
    Unified Facebook scraper (single entry point):
      • Post အသစ်       → full scrape (text, timestamp, comments, engagement)
      • Known post (30-day window အတွင်း) → FULL re-scrape too — engagement
        metrics AND comments are refreshed (Fix #1: no longer just an
        engagement-only update followed by `continue`; new comments are
        discovered and existing comments' `likes` are updated via upsert).
      • Expired post     → 'final' အဖြစ် archive ပြီး skip
    MongoDB (feedback_analytics.contents) သည် dedup/lifecycle state ၏ source of truth ဖြစ်သည်။
    """
    print(f"\n[INFO] Scraping Facebook Page: {page_url} (Target: {max_posts} Posts)")
    scrape_time = datetime.now()   # ← Scrape session ၏ reference time

    # ── 30-Day Lifecycle: expired posts များကို အရင် finalize လုပ်ပြီး
    #    known/final state ကို MongoDB မှ တစ်ကြိမ်တည်း ဖတ်သည် ──
    finalize_expired_posts_db(db)
    known_posts = get_known_posts(db)   # tracking ဖြစ်ပြီး 30-day window အတွင်းရှိသေးသော posts
    final_ids = get_final_post_ids(db)  # archive ဖြစ်ပြီးသား posts (ထပ် scrape မလုပ်)
    print(f"   -> Lifecycle state: {len(known_posts)} active (full re-scrape: engagement + comments) | "
          f"{len(final_ids)} finalized (skip)")
    
    page.goto(page_url, timeout=60000, wait_until="domcontentloaded") 
    page.wait_for_timeout(5000) 
    try:
        page.wait_for_selector("div[aria-posinset]", timeout=15000)
    except Exception:
        print("   -> [WARN] No posts detected after initial load; continuing to scroll...")
    
    print("   -> Scrolling down to securely load posts...")
    
    # 1. Scroll & Wait Loop — drive Facebook's lazy feed loader with window.scrollBy
    #    (keyboard PageDown can miss the feed if focus is elsewhere). Loop until we
    #    have >= max_posts nodes or the count stops growing.
    scroll_attempts = 0
    prev_count = -1
    stale = 0
    while scroll_attempts < 15:
        current_count = page.locator("div[aria-posinset]").count()
        if current_count >= max_posts:
            break
        if current_count == prev_count:
            stale += 1
            if stale >= 3:
                break  # feed stopped growing
        else:
            stale = 0
        prev_count = current_count
        page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        scroll_attempts += 1

    valid_posts = page.locator("div[aria-posinset]").all()[:max_posts]
    print(f"   -> Successfully Locked {len(valid_posts)} posts. Extracting Data...")
    
    results = []          # NEW *and* known active posts → drive Mongo bulk upserts
    debug_records = []    # every post touched this run → JSON debug artifact

    for index, post in enumerate(valid_posts):
        try:
            # Facebook virtualizes the feed, so a captured locator may point to a
            # node that is not yet "visible/stable". scroll_into_view_if_needed()
            # would then time out and abort the whole post. Do a best-effort scroll
            # and never let a scroll failure skip the post — evaluate()-based
            # extraction below works on non-visible nodes anyway.
            try:
                post.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                try:
                    post.evaluate(
                        "node => node.scrollIntoView({block: 'center', behavior: 'instant'})"
                    )
                except Exception:
                    pass
            page.wait_for_timeout(1000)

            # Main Post 'See more' နှိပ်ခြင်း
            see_more_btns = post.locator("div[role='button'], span[dir='auto']", has_text=re.compile(r"see more|ပိုမိုကြည့်ရှုရန်", re.IGNORECASE)).all()
            for btn in see_more_btns:
                try: btn.evaluate("node => node.click()")
                except: pass
                page.wait_for_timeout(500)

            # Main Post Text ကို ယူခြင်း
            msg_locators = post.locator("div[data-ad-comet-preview='message'], div[data-ad-preview='message']")
            if msg_locators.count() == 0:
                continue
            post_text = msg_locators.first.inner_text().strip()
            if not post_text:
                continue

            fb_post_id = f"fb_post_{hashlib.md5(post_text.encode('utf-8')).hexdigest()}"

            # ══════════════════════════════════════════════════════
            # 🌟 UNIFIED LIFECYCLE BRANCHING
            # ══════════════════════════════════════════════════════
            # (1) Final ဖြစ်ပြီးသား post → ထပ်မ scrape တော့ဘဲ skip
            if fb_post_id in final_ids:
                snippet = post_text[:40].replace('\n', ' ')
                print(f"      - Post {index + 1}: 📦 '{snippet}...' already finalized "
                      f"(past {LIFECYCLE_DAYS}-day window) — skipped.")
                debug_records.append({
                    "source_content_id": fb_post_id,
                    "title_or_post": post_text,
                    "lifecycle_status": "final",
                    "run_action": "skipped_finalized",
                    "feedbacks": []
                })
                continue

            # (2) Known post (30-day window အတွင်း) → FULL re-scrape (Fix #1)
            #     Previously this branch only updated engagement metrics and then
            #     `continue`d, entirely skipping the comment-extraction pipeline
            #     below. Known posts now fall through into the SAME full-scrape
            #     pipeline used for brand-new posts, so their comment section is
            #     opened, switched to "All comments", and paginated via
            #     exhaust_view_more_comments — newly posted comments are
            #     discovered and existing comments' `likes` are refreshed by the
            #     upsert logic at the bottom of this function.
            is_known_post = fb_post_id in known_posts
            known_history = []
            if is_known_post:
                known_history = known_posts[fb_post_id].get("engagement_history", [])
                print(f"      - Post {index + 1}: 🔄 known post detected — re-scraping "
                      f"comments too (no longer skipped)...")

            # (3) Full scrape (timestamp, comments, engagement) — runs for BOTH
            #     brand-new posts AND known posts.
            
            # ── Post Timestamp ယူခြင်း (Hover Tooltip Method) ──
            # Facebook scrambles timestamp text with CSS (anti-scraping), so we can't
            # read it directly. Instead, identify the timestamp <a> by its unique href
            # pattern: starts with "?" and contains "__cft__" (relative URL).
            # Then hover to get the tooltip with exact datetime.
            post_timestamp = scrape_time.strftime('%Y-%m-%d %H:%M:%S')
            try:
                time_link = None
                all_links = post.locator("a").all()

                # The timestamp link's href starts with "?" (relative URL with __cft__ param)
                # All other links use absolute URLs (https://...) or paths (/watch/...)
                for link in all_links:
                    try:
                        href = (link.get_attribute("href") or "")
                        if href.startswith("?") and "__cft__" in href:
                            time_link = link
                            break
                    except:
                        continue

                if time_link:
                    # Scroll into view and hover to trigger tooltip
                    try:
                        time_link.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        try:
                            time_link.evaluate(
                                "node => node.scrollIntoView({block: 'center', behavior: 'instant'})"
                            )
                        except Exception:
                            pass
                    page.wait_for_timeout(500)
                    time_link.hover(timeout=3000)
                    page.wait_for_timeout(2000)

                    # Check for tooltip with exact datetime
                    tooltip = page.locator("div[role='tooltip']")
                    if tooltip.count() > 0 and tooltip.first.is_visible():
                        tooltip_text = tooltip.first.inner_text().strip()
                        print(f"        [DEBUG] Tooltip: '{tooltip_text}'")
                        if tooltip_text and re.search(r'\d', tooltip_text):
                            post_timestamp = parse_relative_time(tooltip_text, scrape_time)
                    else:
                        print(f"        [DEBUG] No tooltip appeared, checking aria-label...")
                        # Fallback: check aria-label on the link or its children
                        aria = (time_link.get_attribute("aria-label") or "").strip()
                        if aria and re.search(r'\d', aria):
                            post_timestamp = parse_relative_time(aria, scrape_time)
                            print(f"        [DEBUG] aria-label: '{aria}'")

                    # Move mouse away to dismiss tooltip
                    page.mouse.move(0, 0)
                    page.wait_for_timeout(300)
                else:
                    print(f"        [DEBUG] No timestamp link found for post {index+1}")
            except Exception as e:
                print(f"        [DEBUG] Timestamp error: {e}")

            # ── Post Engagement Metrics (Likes, Shares, Comments count) ──
            total_reactions, total_shares, total_comments = extract_engagement_metrics(post)

            if is_known_post:
                if known_history:
                    prev = known_history[-1]
                    print(f"        Reactions: {total_reactions} (+{total_reactions - prev.get('reactions', 0)}) | "
                          f"Shares: {total_shares} (+{total_shares - prev.get('shares', 0)}) | "
                          f"Comments: {total_comments} (+{total_comments - prev.get('comments', 0)})")
                else:
                    print(f"        Reactions: {total_reactions} | Shares: {total_shares} | "
                          f"Comments: {total_comments}")

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            content_obj = {
                "source_type": "Social",
                "entity_name": entity_name,
                "source_content_id": fb_post_id,
                "title_or_post": post_text,
                "post_timestamp": post_timestamp,
                "total_reactions": total_reactions,
                "total_shares": total_shares,
                "total_comments": total_comments,
                "lifecycle_status": "tracking",
                "first_scraped_at": now_str,
                "last_updated_at": now_str,
                "expires_at": (datetime.now() + timedelta(days=LIFECYCLE_DAYS)).strftime('%Y-%m-%d %H:%M:%S'),
                "scrape_count": 1,
                "feedbacks": [],
                "run_action": "known_post_full_rescrape" if is_known_post else "new_post_full_scrape",
            }

            # ==========================================
            # 🌟 OPEN AND VALIDATE THIS POST'S FULL COMMENTS VIEW
            # ==========================================
            opened = open_comment_container(page, post, post_text)
            target_container = opened["container"]
            dialog_opened = opened["dialog_valid"]
            content_obj["comments_complete"] = True
            content_obj["comment_diagnostics"] = {
                "container_reason": opened["reason"],
            }
            if total_comments > 0 and not dialog_opened:
                content_obj["comments_complete"] = False
                content_obj["comment_diagnostics"]["termination_reason"] = "invalid_comment_container"
                print(f"        [COMMENTS][{fb_post_id}] No validated comment surface: "
                      f"{opened['reason']}")

            # ──────────────────────────────────────────────
            # 🌟 SWITCH TO "ALL COMMENTS" FILTER (hard precondition)
            # ──────────────────────────────────────────────
            sort_result = switch_to_all_comments(target_container, page)
            content_obj["comment_diagnostics"].update({
                "all_comments_confirmed": sort_result["confirmed"],
                "active_sort_label": sort_result.get("active_label", ""),
                "sort_attempts": sort_result["attempts"],
                "sort_reason": sort_result["reason"],
                "settle_timeouts": sort_result.get("settle_timeouts", 0),
            })
            if not dialog_opened or not sort_result["confirmed"]:
                content_obj["comments_complete"] = False
                content_obj["comment_diagnostics"].setdefault(
                    "termination_reason",
                    "invalid_comment_container" if not dialog_opened else "all_comments_unconfirmed",
                )
                results.append(content_obj)
                debug_records.append(content_obj)
                print(f"        [COMMENTS][{fb_post_id}] Extraction skipped: "
                      f"{content_obj['comment_diagnostics']['termination_reason']}")
                close_comment_dialog(page, opened["dialog"])
                continue

            # ==========================================
            # 🌟 TEXT EXTRACTION & MEDIA FILTERING
            #    Direct comments only — skip threaded replies
            #
            #    Facebook virtualizes the comment list: older (off-screen)
            #    comment articles are unmounted from the DOM as we scroll, so a
            #    single post-pagination snapshot would only capture the last
            #    visible (newest) window. To collect ALL direct comments we
            #    harvest INCREMENTALLY on every pagination iteration (via the
            #    harvest_cb callback) and then run one FINAL pass afterwards.
            #    Dedup is handled by seen_ids + fb_comm_id across all passes.
            # ==========================================
            seen_ids = set()   # deduplicate within same post (shared across passes)
            harvest_stats = {
                "unknown_depth": 0,
                "detached": 0,
                "parse_failures": 0,
                "harvest_errors": 0,
            }

            def _harvest():
                try:
                    return harvest_comments(
                        target_container=target_container,
                        post_id=fb_post_id,
                        scrape_time=scrape_time,
                        seen_ids=seen_ids,
                        content_obj=content_obj,
                        stats=harvest_stats,
                    )
                except Exception as exc:
                    harvest_stats["harvest_errors"] += 1
                    content_obj["comments_complete"] = False
                    content_obj.setdefault("comment_diagnostics", {})["harvest_error"] = (
                        f"{type(exc).__name__}: {exc}"
                    )
                    print(f"        [HARVEST][{fb_post_id}] {type(exc).__name__}: {exc}")
                    raise

            # ──────────────────────────────────────────────
            # 🌟 EXHAUST ALL "View more comments" (direct comments only)
            #    Harvest each iteration so nothing is lost to virtualization.
            # ──────────────────────────────────────────────
            exhaust_view_more_comments(
                target_container, page, dialog_opened,
                post_locator=post, harvest_cb=_harvest
            )

            # ── FINAL harvest pass: capture the last-loaded window ──
            _harvest()

            results.append(content_obj)
            debug_records.append(content_obj)   # new posts also appear in the JSON debug artifact
            snippet = post_text[:40].replace('\n', ' ') + "..." if len(post_text) > 40 else post_text
            print(f"      - Post {index + 1}: Saved '{snippet}' with {len(content_obj['feedbacks'])} comments.")
            
            # Close only the dialog correlated with this post.
            close_comment_dialog(page, opened["dialog"])
                
        except Exception as e:
            print(f"      - Post {index + 1}: Error processing -> {str(e)}")
            continue

    # ── 30-Day Lifecycle: New AND known active posts များကို MongoDB (source of truth) သို့ တိုက်ရိုက် upsert ──
    if results:
        now = datetime.now()
        content_ops = []
        feedback_ops = []

        for content_obj in results:
            post_id = content_obj["source_content_id"]
            feedbacks = content_obj.get("feedbacks", [])

            try:
                post_ts_dt = datetime.strptime(
                    content_obj.get("post_timestamp", ""), '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                post_ts_dt = now

            engagement_snapshot = {
                "scraped_at": now,
                "reactions": content_obj.get("total_reactions", 0),
                "shares": content_obj.get("total_shares", 0),
                "comments": content_obj.get("total_comments", 0),
                "comment_count_extracted": len(feedbacks),
            }

            content_ops.append(UpdateOne(
                {"_id": post_id},
                {
                    "$set": {
                        "source_type": content_obj.get("source_type", "Social"),
                        "entity_name": entity_name,
                        "page_url": page_url,
                        "title_or_post": content_obj.get("title_or_post", ""),
                        "post_timestamp": post_ts_dt,
                        "total_reactions": content_obj.get("total_reactions", 0),
                        "total_shares": content_obj.get("total_shares", 0),
                        "total_comments": content_obj.get("total_comments", 0),
                        "lifecycle_status": "tracking",
                        "last_updated_at": now,
                        "comment_count": len(feedbacks),
                    },
                    "$setOnInsert": {
                        "first_scraped_at": now,
                        "expires_at": now + timedelta(days=LIFECYCLE_DAYS),
                    },
                    "$inc": {"scrape_count": 1},
                    "$push": {"engagement_history": engagement_snapshot},
                },
                upsert=True
            ))

            for fb in feedbacks:
                fb_id = fb.get("id", "")
                if not fb_id:
                    continue
                try:
                    fb_ts = datetime.strptime(fb.get("timestamp", ""), '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    fb_ts = now
                feedback_ops.append(UpdateOne(
                    {"_id": fb_id},
                    {"$set": {
                        "content_id": post_id,
                        "entity_name": entity_name,
                        "source_type": content_obj.get("source_type", "Social"),
                        "author": fb.get("author", "Unknown"),
                        "raw_text": fb.get("text", ""),
                        "likes": fb.get("likes", 0),
                        "feedback_date": fb_ts,
                        "scraped_at": now,
                    }},
                    upsert=True
                ))

        if content_ops:
            res = db[CONTENTS_COLLECTION].bulk_write(content_ops)
            print(f"\n[MONGO] Contents:  {res.upserted_count} inserted, {res.modified_count} updated.")
            # Safety: legacy docs (ingest ဖြင့် အရင်ရောက်ပြီးသား) တွင်
            # expires_at / first_scraped_at မရှိလျှင် ဖြည့်ပေးသည် —
            # မရှိပါက lifecycle queries (expires_at $gt/$lte) က မမိနိုင်ပါ။
            db[CONTENTS_COLLECTION].update_many(
                {"lifecycle_status": "tracking", "expires_at": {"$exists": False}},
                {"$set": {"expires_at": now + timedelta(days=LIFECYCLE_DAYS)}})
            db[CONTENTS_COLLECTION].update_many(
                {"first_scraped_at": {"$exists": False}},
                {"$set": {"first_scraped_at": now}})
        if feedback_ops:
            res = db[FEEDBACKS_COLLECTION].bulk_write(feedback_ops)
            print(f"[MONGO] Feedbacks: {res.upserted_count} inserted, {res.modified_count} updated.")
        print(f"[LIFECYCLE] {len(results)} post(s) (new + known re-scraped) processed for "
              f"{LIFECYCLE_DAYS}-day engagement/comment tracking (MongoDB).")

    # JSON File အဖြစ် Save မည် — every post touched this run (new / known-rescrape / skipped)
    try:
        with open(output_filename, "w", encoding="utf-8") as json_file:
            json.dump(debug_records, json_file, ensure_ascii=False, indent=4)
        print(f"\n[SUCCESS] Debug data exported to: {output_filename} ({len(debug_records)} posts)")
    except Exception as e:
        print(f"\n[ERROR] Failed to save JSON file: {str(e)}")

    return results

# ==========================================
# အပိုင်း (၅) - Other Scrapers
# ==========================================
FOODPANDA_NAVIGATION_TIMEOUT_MS = 60000
FOODPANDA_ACTION_TIMEOUT_MS = 4000
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
    author_known = author and author.casefold() not in FOODPANDA_GENERIC_AUTHORS
    date_known = bool(date)
    if source == 'dom':
        return author_known and date_known
    return author_known and date_known and bool(record.get('rating') is not None or len(text) >= 3)


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
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest() if canonical else ''


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
                    "nodes.map(n => n.innerText||'').join('\\x1e') !== old; }",
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
            'author': record.get('author') or 'Unknown',
            'text': record['text'], 'raw_text': record['text'],
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
                const sig = nodes.map(n => n.innerText || '').join('\\x1e');
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
        if modal_open:
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
        if modal_open:
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
        if title:
            return title
    except Exception:
        pass
    path_name = unquote(urlparse(shop_url).path.rstrip('/').split('/')[-1]).replace('-', ' ')
    return normalize_foodpanda_text(path_name).title() or 'Foodpanda shop'


def scrape_foodpanda_reviews(page, shop_url, entity_name):
    print(f"\n[INFO] Scraping Foodpanda URL: {shop_url}")
    shop_uuid = f"fp_shop_{hashlib.sha256(shop_url.encode('utf-8')).hexdigest()[:16]}"
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

# ==========================================
# အပိုင်း (၆) - Interactive CLI (Main Execution)
# ==========================================
def run_facebook_scrape(target_url, entity_name, max_posts, headless=False):
    """
    Unified Facebook scrape runner — interactive mode နှင့် cron (--url) mode
    နှစ်ခုလုံးက ဤ function တစ်ခုတည်းကိုသာ သုံးသည်။
      • Post အသစ်  → full scrape
      • Known post → full re-scrape (engagement + comments)
      • Expired    → finalize & skip
    """
    client, db = get_db()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            load_cookies(context, "cookies.json")
            page = context.new_page()

            scrape_facebook_page_feed(page, target_url, entity_name, max_posts, db)

            browser.close()

        show_tracking_status_db(db)
    finally:
        client.close()


def run_other_scrape(source, target_url, entity_name, headless=False):
    if not normalize_ui_text(target_url):
        raise ValueError(f'--url is required for source {source}')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            if source == 'foodpanda':
                scrape_foodpanda_reviews(page, target_url, entity_name)
            elif source == 'blog':
                scrape_business_blog(page, target_url, entity_name)
            else:
                raise ValueError(f'Unsupported source: {source}')
        finally:
            browser.close()
    export_to_json(entity_name or source)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Unified scraper: new posts are fully scraped; already-scraped posts "
            f"within the {LIFECYCLE_DAYS}-day window are fully re-scraped; "
            "expired posts are finalized. MongoDB (feedback_analytics.contents) is "
            "the source of truth — tracking_state.json is no longer used."
        )
    )
    parser.add_argument("--source", choices=('facebook', 'foodpanda', 'blog'), default='facebook',
                        help="Scraper source for --url (default: facebook)")
    parser.add_argument("--url", help="Source URL (enables non-interactive/cron mode)")
    parser.add_argument("--entity", default="", help="Business/Page/shop name (e.g. 'KFC Myanmar')")
    parser.add_argument("--max-posts", type=int, default=10,
                        help="Maximum number of posts to scan (default: 10)")
    parser.add_argument("--headless", action="store_true",
                        help="Run the browser headless (required for cron/Task Scheduler)")
    parser.add_argument("--status", action="store_true",
                        help="Show tracking status from MongoDB and exit")
    args = parser.parse_args()

    # ── Non-interactive: --status (no browser needed) ──
    if args.status:
        client, db = get_db()
        try:
            show_tracking_status_db(db)
        finally:
            client.close()
        return

    # ── Non-interactive: --url (cron / Task Scheduler friendly, no input() prompts) ──
    # Example:
    #   python scraping.py --url https://www.facebook.com/LotteriaMyanmar --entity "Lotteria" --max-posts 10 --headless
    if args.url:
        if args.source == 'facebook':
            run_facebook_scrape(args.url, args.entity, args.max_posts, headless=args.headless)
        else:
            run_other_scrape(args.source, args.url, args.entity, headless=args.headless)
        return

    # ── Interactive mode ──
    print("==================================================")
    print("🚀 Unified Scraping CLI (with Facebook Auth)")
    print("==================================================")

    print("Select Source Type:")
    print(f"1. Facebook Page (Post & Comments — unified: new and known posts full scrape, "
          f"{LIFECYCLE_DAYS}-day lifecycle)")
    print("2. Foodpanda/Grab Shop (Reviews)")
    print("3. Business Blog (Articles)")
    print("4. 📊 View tracking status (MongoDB)")

    choice = input("Enter choice (1/2/3/4): ").strip()

    # ── Option 4: View status (no browser needed) ──
    if choice == '4':
        client, db = get_db()
        try:
            show_tracking_status_db(db)
        finally:
            client.close()
        return

    if choice not in ('1', '2', '3'):
        print("[ERROR] Invalid choice. Exiting.")
        return

    target_url = input("Enter the full URL: ").strip()
    entity_name = input("Enter Business/Page Name (e.g., KFC Myanmar): ").strip()

    # ── Option 1: Unified Facebook scrape ──
    if choice == '1':
        max_posts_input = input("Enter maximum number of posts to scrape (e.g., 10): ").strip()
        max_posts = int(max_posts_input) if max_posts_input.isdigit() else 10
        run_facebook_scrape(target_url, entity_name, max_posts, headless=False)
        return

    # ── Options 2/3: Other scrapers (unchanged) ──
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        if choice == '2':
            scrape_foodpanda_reviews(page, target_url, entity_name)
        elif choice == '3':
            scrape_business_blog(page, target_url, entity_name)

        browser.close()

    export_to_json(entity_name)

if __name__ == "__main__":
    main()
