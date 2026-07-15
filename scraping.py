import json
import hashlib
from datetime import datetime, timedelta
import os
from playwright.sync_api import sync_playwright
import re

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
# အပိုင်း (၄) - Dynamic Scrapers
# ==========================================

def scrape_facebook_page_feed(page, page_url, entity_name, max_posts, output_filename="facebook_data.json"):
    print(f"\n[INFO] Scraping Facebook Page: {page_url} (Target: {max_posts} Posts)")
    scrape_time = datetime.now()   # ← Scrape session ၏ reference time
    
    page.goto(page_url, timeout=60000, wait_until="domcontentloaded") 
    page.wait_for_timeout(5000) 
    
    print("   -> Scrolling down to securely load posts...")
    
    # 1. Scroll & Wait Loop
    valid_posts = []
    scroll_attempts = 0
    while len(valid_posts) < max_posts and scroll_attempts < 15:
        current_locators = page.locator("div[aria-posinset]").all()
        if len(current_locators) >= max_posts:
            valid_posts = current_locators[:max_posts]
            break
        page.keyboard.press("PageDown")
        page.keyboard.press("PageDown") 
        page.wait_for_timeout(3000) 
        scroll_attempts += 1

    valid_posts = page.locator("div[aria-posinset]").all()[:max_posts]
    print(f"   -> Successfully Locked {len(valid_posts)} posts. Extracting Data...")
    
    results = [] 

    for index, post in enumerate(valid_posts):
        try:
            post.scroll_into_view_if_needed(timeout=2000)
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
                    time_link.scroll_into_view_if_needed(timeout=2000)
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
            total_reactions = 0
            total_shares = 0
            total_comments = 0
            try:
                metrics = post.evaluate("""(node) => {
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
            except:
                pass

            content_obj = {
                "source_type": "Social",
                "entity_name": entity_name,
                "source_content_id": fb_post_id,
                "title_or_post": post_text,
                "post_timestamp": post_timestamp,
                "total_reactions": total_reactions,
                "total_shares": total_shares,
                "total_comments": total_comments,
                "feedbacks": []
            }

            # ==========================================
            # 🌟 OPEN FULL COMMENTS VIEW
            # ==========================================
            # Strategy 1: Click "X comments" counter (e.g., "16 comments")
            #   → This reliably opens a full dialog showing ALL comments
            # Strategy 2 (fallback): Click "Comment" action button
            dialog_locator = page.locator("div[role='dialog']")

            try:
                post.evaluate("""(node) => {
                    const els = Array.from(node.querySelectorAll('span, a, div'));
                    const link = els.find(el => {
                        const t = el.textContent.trim();
                        return /^\\d+\\s*(comments?|မှတ်ချက်)/i.test(t) && t.length < 30;
                    });
                    if (link) link.click();
                }""")
            except:
                pass
            page.wait_for_timeout(3000)

            # Check if dialog opened
            dialog_opened = dialog_locator.count() > 0 and dialog_locator.first.is_visible()

            if not dialog_opened:
                # Fallback: Click "Comment" action button
                try:
                    post.evaluate("""(node) => {
                        const btns = Array.from(node.querySelectorAll("div[role='button']"));
                        const commentBtn = btns.find(b => b.innerText.toLowerCase().includes('comment') || b.innerText.includes('မှတ်ချက်'));
                        if(commentBtn) commentBtn.click();
                    }""")
                except:
                    pass
                page.wait_for_timeout(3000)
                dialog_opened = dialog_locator.count() > 0 and dialog_locator.first.is_visible()

            if dialog_opened:
                target_container = dialog_locator.first
            else:
                target_container = post

            # ──────────────────────────────────────────────
            # 🌟 EXHAUST ALL "View more comments" (direct comments only)
            # ──────────────────────────────────────────────

            # Scroll inside dialog to trigger lazy-loading of comments
            if dialog_opened:
                for _ in range(5):
                    target_container.evaluate("(node) => { node.scrollTop = node.scrollHeight; }")
                    page.wait_for_timeout(1500)
            else:
                # Inline mode: scroll the page itself
                for _ in range(3):
                    post.scroll_into_view_if_needed(timeout=2000)
                    page.keyboard.press("End")
                    page.wait_for_timeout(1500)

            # Click "View more comments" — using Playwright native text locator
            for _ in range(25):
                clicked = False
                try:
                    view_more = target_container.get_by_text(
                        re.compile(r'view\s+(more\s+comment|previous\s+comment|\d+\s+more\s+comment)|မှတ်ချက်များ\s*ထပ်မံ|ယခင်မှတ်ချက်', re.IGNORECASE)
                    ).first
                    if view_more.is_visible(timeout=2000):
                        view_more.click(timeout=3000)
                        clicked = True
                except:
                    pass

                if not clicked:
                    # JS fallback: broader search across ALL span/div/a elements
                    try:
                        clicked = target_container.evaluate("""(node) => {
                            const els = Array.from(node.querySelectorAll('*'));
                            const btn = els.find(el => {
                                const t = el.textContent.trim().toLowerCase();
                                if (t.length > 50) return false;
                                return t === 'view more comments' ||
                                       t === 'view previous comments' ||
                                       (t.includes('view') && t.includes('more') && t.includes('comment')) ||
                                       t.includes('မှတ်ချက်များ ထပ်မံ') ||
                                       t.includes('ယခင်မှတ်ချက်');
                            });
                            if (btn) { btn.click(); return true; }
                            return false;
                        }""")
                    except:
                        clicked = False

                if not clicked:
                    break
                page.wait_for_timeout(2500)
                # Scroll again after expanding
                if dialog_opened:
                    target_container.evaluate("(node) => { node.scrollTop = node.scrollHeight; }")
                    page.wait_for_timeout(1000)

            # Expand long comment texts with 'See more'
            target_container.evaluate("""(node) => {
                node.querySelectorAll("div[role='button'], span[dir='auto']").forEach(b => {
                    if(b.innerText.match(/see more|ပိုမိုကြည့်ရှုရန်/i)) b.click();
                });
            }""")
            page.wait_for_timeout(1000)

            # ==========================================
            # 🌟 TEXT EXTRACTION & MEDIA FILTERING
            #    Direct comments only — skip threaded replies
            # ==========================================
            articles = target_container.locator("div[role='article']").all()
            
            seen_ids = set()   # deduplicate within same post

            for article in articles:
                try:
                    # ── REPLY FILTER: Skip threaded replies via aria-label ──
                    aria_label = article.get_attribute("aria-label") or ""
                    if "reply" in aria_label.lower() or "ပြန်လည်ဖြေကြားချက်" in aria_label:
                        continue

                    raw_text = article.inner_text().strip()
                    if not raw_text:
                        continue
                        
                    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                    if len(lines) < 2:
                        continue 
                        
                    author = lines[0]
                    
                    # 1. Skip if the Author name matches the entered Entity Name
                    #    (Guard: empty entity_name "" is substring of everything)
                    if entity_name and entity_name.lower() in author.lower():
                        continue
                        
                    # 2. STRONGER FILTER: Skip page's own comments (tagged Author/Admin)
                    is_page_reply = False
                    for line in lines:
                        if line.lower() in ['author', 'admin', 'စာရေးသူ']:
                            is_page_reply = True
                            break
                            
                    if is_page_reply:
                        continue

                    # 3. Extract timestamp from the article element
                    comment_timestamp = extract_comment_timestamp(article, scrape_time)

                    # 4. Clean up the actual comment text
                    ignore_badges = ['top fan', 'follow', 'ရှေ့တန်းပရိသတ်', 'super fan']
                    ui_stops = [
                        'like', 'reply', 'share', 'edited', 'see translation',
                        'ကြိုက်တယ်', 'ပြန်ပြန်ပြောရန်', 'ဝေမျှရန်', 'send message'
                    ]
                    
                    comment_text = ""
                    
                    for line in lines[1:]:
                        low_line = line.lower()
                        
                        # Stop at UI button labels or time tokens
                        if (low_line in ui_stops
                                or re.match(r'^\d+[mhdwy]$', low_line)
                                or low_line.endswith(' shares')):
                            break
                            
                        # Skip fan badges or image descriptions
                        if (low_line in ignore_badges
                                or "may be an image of" in low_line
                                or "may be an illustration" in low_line):
                            continue
                        
                        comment_text += line + " "
                        
                    comment_text = comment_text.strip()
                    
                    # Save only if there's actual text and it's not a duplicate
                    if len(comment_text) > 1 and comment_text != post_text:
                        fb_comm_id = f"fb_comm_{hashlib.md5(comment_text.encode('utf-8')).hexdigest()[:10]}"
                        
                        if fb_comm_id in seen_ids:
                            continue
                        seen_ids.add(fb_comm_id)

                        # Extract comment likes/reactions count
                        comment_likes = 0
                        try:
                            # Facebook shows comment reactions as a button with aria-label
                            # e.g. "5" or "1" near the comment, or in a small reaction badge
                            comment_likes = article.evaluate("""(node) => {
                                // Look for reaction count near comment
                                const btns = Array.from(node.querySelectorAll('[aria-label]'));
                                for (const btn of btns) {
                                    const label = btn.getAttribute('aria-label') || '';
                                    // e.g. "5 reactions" "1 like" "3 people reacted"
                                    const m = label.match(/(\\d+)\\s*(reaction|like|people|person|others)/i);
                                    if (m) return parseInt(m[1]);
                                }
                                // Also check for small count spans (e.g. just "5" next to reaction icon)
                                const spans = Array.from(node.querySelectorAll('span'));
                                for (const s of spans) {
                                    const t = s.textContent.trim();
                                    if (/^\\d+$/.test(t) && parseInt(t) < 10000) {
                                        // Check if this span is near a reaction button/icon
                                        const parent = s.closest('[role="button"]');
                                        if (parent) return parseInt(t);
                                    }
                                }
                                return 0;
                            }""")
                        except:
                            pass

                        content_obj["feedbacks"].append({
                            "id": fb_comm_id,
                            "author": author,
                            "text": comment_text,
                            "timestamp": comment_timestamp,
                            "likes": comment_likes
                        })
                        
                except Exception as e:
                    continue

            results.append(content_obj)
            snippet = post_text[:40].replace('\n', ' ') + "..." if len(post_text) > 40 else post_text
            print(f"      - Post {index + 1}: Saved '{snippet}' with {len(content_obj['feedbacks'])} comments.")
            
            # Popup Modal ပိတ်မည်
            if dialog_locator.count() > 0 and dialog_locator.first.is_visible():
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
                
        except Exception as e:
            print(f"      - Post {index + 1}: Error processing -> {str(e)}")
            continue

    # JSON File အဖြစ် Save မည်
    try:
        with open(output_filename, "w", encoding="utf-8") as json_file:
            json.dump(results, json_file, ensure_ascii=False, indent=4)
        print(f"\n[SUCCESS] Data successfully exported to: {output_filename}")
    except Exception as e:
        print(f"\n[ERROR] Failed to save JSON file: {str(e)}")

    return results

# ==========================================
# အပိုင်း (၅) - Other Scrapers
# ==========================================
def scrape_foodpanda_reviews(page, shop_url, entity_name):
    print(f"\n[INFO] Scraping Foodpanda URL: {shop_url}")
    shop_uuid = f"fp_shop_{hashlib.md5(shop_url.encode('utf-8')).hexdigest()[:10]}"
    content_obj = get_or_create_content('Platform', entity_name, shop_uuid, f"{entity_name} Reviews")
    
    page.goto(shop_url)
    page.wait_for_timeout(4000)
    reviews = page.locator(".review-component__text-content").all_text_contents()
    
    saved_count = 0
    for text in reviews:
        if text.strip():
            unique_id = f"fp_rev_{hashlib.md5(text.encode('utf-8')).hexdigest()}"
            add_feedback(content_obj, unique_id, text.strip())
            saved_count += 1
    print(f"   -> Extracted {saved_count} reviews.")

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
def main():
    print("==================================================")
    print("🚀 JSON Data Ingestion CLI (with Facebook Auth)")
    print("==================================================")
    
    print("Select Source Type:")
    print("1. Facebook Page (Post & Comments)")
    print("2. Foodpanda/Grab Shop (Reviews)")
    print("3. Business Blog (Articles)")
    
    choice = input("Enter choice (1/2/3): ").strip()
    target_url = input("Enter the full URL: ").strip()
    entity_name = input("Enter Business/Page Name (e.g., KFC Myanmar): ").strip()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        context = browser.new_context()
        
        if choice == '1':
            load_cookies(context, "cookies.json") 
            
        page = context.new_page()
        
        if choice == '1':
            max_posts_input = input("Enter maximum number of posts to scrape (e.g., 10): ").strip()
            max_posts = int(max_posts_input) if max_posts_input.isdigit() else 10
            scrape_facebook_page_feed(page, target_url, entity_name, max_posts)
            
        elif choice == '2':
            scrape_foodpanda_reviews(page, target_url, entity_name)
            
        elif choice == '3':
            scrape_business_blog(page, target_url, entity_name)
            
        else:
            print("[ERROR] Invalid choice. Exiting.")
            
        browser.close()
        
    export_to_json(entity_name)

if __name__ == "__main__":
    main()
