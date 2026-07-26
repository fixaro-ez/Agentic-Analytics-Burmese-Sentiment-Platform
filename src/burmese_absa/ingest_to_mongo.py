"""
MongoDB Data Ingestion Script
──────────────────────────────
Scraped JSON files (facebook_data.json, etc.) ကို MongoDB container ထဲသို့ ingest လုပ်ပေးသည်။

⚠️  IMPORTANT — Facebook data is now written to MongoDB DIRECTLY by scraping.py:
  scraping.py (unified scraper) သည် contents/feedbacks collections ထဲသို့
  တိုက်ရိုက် upsert လုပ်ပြီး engagement_history ကိုလည်း $push လုပ်ပါသည်။
  ထို့ကြောင့် facebook_data.json ကို ဤ script ဖြင့် ထပ် ingest လုပ်ပါက
  engagement_history entries များ ပွားနိုင်ပါသည်။
  Safety guard: document ၏ last_updated_at သည် JSON record ထက်
  equal-or-newer ဖြစ်နေလျှင် ထို record ကို skip လုပ်ပါသည် (duplicate $push မဖြစ်စေရန်)။
  ဤ script ကို non-Facebook sources နှင့် backfill အတွက်သာ သုံးပါ။

MongoDB Schema Design:
  Database: feedback_analytics
  Collections:
    - contents     → Posts/Reviews/Articles (parent documents)
    - feedbacks    → Comments/Reviews (child documents, linked by content_id)

Key Behaviors:
  - Uses UPSERT (insert-or-update) — never deletes existing documents.
  - Posts with lifecycle_status="final" are permanently retained for analytics.
  - Engagement history is preserved across re-scrapes via $push.
  - Comment likes (per-comment) are stored alongside each feedback document.

Usage:
  python ingest_to_mongo.py                          # Default: facebook_data.json
  python ingest_to_mongo.py my_data.json             # Custom file
  python ingest_to_mongo.py file1.json file2.json    # Multiple files
"""

import json
import sys
import os
from datetime import datetime
from pymongo import MongoClient, UpdateOne, ASCENDING, DESCENDING

# ==========================================
# Configuration
# ==========================================
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "feedback_analytics"
CONTENTS_COLLECTION = "contents"
FEEDBACKS_COLLECTION = "feedbacks"


def connect_to_mongo():
    """MongoDB container သို့ ချိတ်ဆက်ခြင်း"""
    print(f"\n[INFO] Connecting to MongoDB at {MONGO_URI}...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    
    # Connection test
    client.admin.command('ping')
    print("[SUCCESS] Connected to MongoDB successfully!")
    
    return client


def parse_timestamp(ts_string):
    """Timestamp string ကို datetime object ပြောင်းပေးသည်"""
    if not ts_string:
        return datetime.now()
    try:
        return datetime.strptime(ts_string, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            return datetime.fromisoformat(ts_string)
        except ValueError:
            return datetime.now()


def ingest_json_file(db, filepath):
    """
    JSON ဖိုင်တစ်ခုကို ဖတ်ပြီး MongoDB သို့ upsert (insert-or-update) လုပ်ခြင်း။
    Final status posts ကို ဘယ်တော့မှ delete မလုပ်ဘဲ permanently retain လုပ်သည်။
    
    Schema:
      contents collection:
        {
          _id: source_content_id,
          source_type: "Social",
          entity_name: "KFC Myanmar",
          title_or_post: "...",
          post_timestamp: ISODate(...),
          total_reactions: 4200,
          total_shares: 14,
          total_comments: 8,
          lifecycle_status: "tracking" | "final",
          first_scraped_at: ISODate(...),
          last_updated_at: ISODate(...),
          expires_at: ISODate(...),
          scrape_count: 3,
          comment_count: 9,
          engagement_history: [
            { scraped_at: ..., reactions: ..., shares: ..., comments: ... }
          ]
        }
      
      feedbacks collection:
        {
          _id: feedback_id (fb_comm_...),
          content_id: source_content_id (foreign key),
          entity_name: "KFC Myanmar",
          author: "Zin Nyein Aung",
          raw_text: "...",
          likes: 68,
          feedback_date: ISODate(...),
          scraped_at: ISODate(...)
        }
    """
    print(f"\n{'='*50}")
    print(f"📂 Processing: {filepath}")
    print(f"{'='*50}")
    
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        return
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        print("[ERROR] JSON root must be an array.")
        return
    
    contents_col = db[CONTENTS_COLLECTION]
    feedbacks_col = db[FEEDBACKS_COLLECTION]
    
    now = datetime.now()
    content_ops = []
    feedback_ops = []
    
    total_contents = 0
    total_feedbacks = 0
    skipped_contents = 0
    
    # ── Freshness guard: scraping.py က တိုက်ရိုက်ရေးပြီးသား documents များ၏
    #    last_updated_at ကို ကြိုတင်ဖတ်ထားသည် (duplicate $push ကာကွယ်ရန်) ──
    all_ids = [item.get("source_content_id", "") for item in data
               if isinstance(item, dict) and item.get("source_content_id")]
    existing_updates = {
        doc["_id"]: doc.get("last_updated_at")
        for doc in contents_col.find({"_id": {"$in": all_ids}}, {"last_updated_at": 1})
    }
    
    for item in data:
        source_content_id = item.get("source_content_id", "")
        if not source_content_id:
            continue
        
        # ── Content document (Upsert) ──
        post_ts = parse_timestamp(item.get("post_timestamp", ""))
        first_scraped_at = parse_timestamp(item.get("first_scraped_at", ""))
        last_updated_at = parse_timestamp(item.get("last_updated_at", ""))
        expires_at = parse_timestamp(item.get("expires_at", ""))
        
        # ── Skip if the DB already has equal-or-newer data for this post
        #    (scraping.py wrote it directly — avoid duplicating engagement_history) ──
        existing_lu = existing_updates.get(source_content_id)
        if isinstance(existing_lu, datetime) and existing_lu >= last_updated_at:
            skipped_contents += 1
            continue
        
        # Build the $set update — always update these fields
        set_fields = {
            "source_type": item.get("source_type", "Unknown"),
            "entity_name": item.get("entity_name", ""),
            "title_or_post": item.get("title_or_post", ""),
            "post_timestamp": post_ts,
            "total_reactions": item.get("total_reactions", 0),
            "total_shares": item.get("total_shares", 0),
            "total_comments": item.get("total_comments", 0),
            "lifecycle_status": item.get("lifecycle_status", "tracking"),
            "last_updated_at": last_updated_at,
            "expires_at": expires_at,
            "scrape_count": item.get("scrape_count", 1),
            "comment_count": len(item.get("feedbacks", [])),
            "ingested_at": now,
        }
        overall_rating = item.get("overall_rating")
        if overall_rating is not None:
            set_fields["overall_rating"] = overall_rating
        
        # $setOnInsert — only set on first insert (preserve original first_scraped_at)
        set_on_insert = {
            "first_scraped_at": first_scraped_at,
        }
        
        # Build the engagement snapshot for this scrape
        engagement_snapshot = {
            "scraped_at": now,
            "reactions": item.get("total_reactions", 0),
            "shares": item.get("total_shares", 0),
            "comments": item.get("total_comments", 0),
            "comment_count_extracted": len(item.get("feedbacks", [])),
        }
        
        content_ops.append(
            UpdateOne(
                {"_id": source_content_id},
                {
                    "$set": set_fields,
                    "$setOnInsert": set_on_insert,
                    "$push": {"engagement_history": engagement_snapshot},
                },
                upsert=True
            )
        )
        total_contents += 1
        
        # ── Feedback documents (Upsert each comment/review) ──
        for fb in item.get("feedbacks", []):
            feedback_id = fb.get("id") or fb.get("source_feedback_id", "")
            if not feedback_id:
                continue

            fb_ts = parse_timestamp(fb.get("timestamp") or fb.get("feedback_date", ""))

            feedback_doc = {
                "content_id": source_content_id,
                "entity_name": item.get("entity_name", ""),
                "source_type": item.get("source_type", "Unknown"),
                "author": fb.get("author", "Unknown"),
                "raw_text": fb.get("text") or fb.get("raw_text", ""),
                "likes": fb.get("likes", 0),
                "feedback_date": fb_ts,
                "scraped_at": now
            }
            if fb.get("rating") is not None:
                feedback_doc["rating"] = fb.get("rating")
            
            feedback_ops.append(
                UpdateOne(
                    {"_id": feedback_id},
                    {"$set": feedback_doc},
                    upsert=True
                )
            )
            total_feedbacks += 1
    
    # ── Bulk Write ──
    if content_ops:
        result = contents_col.bulk_write(content_ops)
        print(f"   📝 Contents:  {result.upserted_count} inserted, "
              f"{result.modified_count} updated (total: {total_contents})")
    
    if feedback_ops:
        result = feedbacks_col.bulk_write(feedback_ops)
        print(f"   💬 Feedbacks: {result.upserted_count} inserted, "
              f"{result.modified_count} updated (total: {total_feedbacks})")
    
    if skipped_contents:
        print(f"   ⏭️  Skipped:   {skipped_contents} content(s) — DB already has "
              f"equal-or-newer data (written directly by scraping.py).")
    
    if not content_ops and not feedback_ops:
        print("   [WARNING] No data to ingest.")
    
    return total_contents, total_feedbacks


def create_indexes(db):
    """Useful indexes for Time-Series analytics, lifecycle queries, and comment-like analysis"""
    contents_col = db[CONTENTS_COLLECTION]
    feedbacks_col = db[FEEDBACKS_COLLECTION]
    
    # Contents indexes
    contents_col.create_index("entity_name")
    contents_col.create_index("post_timestamp")
    contents_col.create_index("source_type")
    contents_col.create_index("lifecycle_status")
    contents_col.create_index("total_reactions")
    # Compound: analytics queries filtering by entity + time
    contents_col.create_index([("entity_name", ASCENDING), ("post_timestamp", DESCENDING)])
    # Compound: lifecycle management queries
    contents_col.create_index([("lifecycle_status", ASCENDING), ("expires_at", ASCENDING)])
    
    # Feedbacks indexes
    feedbacks_col.create_index("content_id")
    feedbacks_col.create_index("entity_name")
    feedbacks_col.create_index("feedback_date")
    feedbacks_col.create_index("author")
    feedbacks_col.create_index("likes")
    feedbacks_col.create_index([("entity_name", ASCENDING), ("feedback_date", DESCENDING)])
    # Compound: find top-liked comments per post
    feedbacks_col.create_index([("content_id", ASCENDING), ("likes", DESCENDING)])
    
    print("\n[INFO] Indexes created for efficient querying (including lifecycle & comment likes).")


def show_summary(db):
    """Ingestion ပြီးနောက် summary ပြခြင်း"""
    contents_col = db[CONTENTS_COLLECTION]
    feedbacks_col = db[FEEDBACKS_COLLECTION]
    
    print(f"\n{'='*50}")
    print(f"📊 Database Summary: {DB_NAME}")
    print(f"{'='*50}")
    
    total_contents = contents_col.count_documents({})
    total_feedbacks = feedbacks_col.count_documents({})
    tracking_count = contents_col.count_documents({"lifecycle_status": "tracking"})
    final_count = contents_col.count_documents({"lifecycle_status": "final"})
    
    print(f"   Total Contents (Posts/Reviews):  {total_contents}")
    print(f"   Total Feedbacks (Comments):      {total_feedbacks}")
    print(f"   🔄 Tracking (active):            {tracking_count}")
    print(f"   📦 Final (archived):             {final_count}")
    
    # Entity breakdown
    pipeline = [
        {"$group": {"_id": "$entity_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    print(f"\n   By Entity:")
    for doc in contents_col.aggregate(pipeline):
        print(f"     • {doc['_id'] or '(unnamed)'}: {doc['count']} posts")
    
    # Top posts by reactions
    top_reactions = contents_col.find(
        {"total_reactions": {"$gt": 0}},
        {"title_or_post": 1, "total_reactions": 1}
    ).sort("total_reactions", DESCENDING).limit(3)
    
    top_list = list(top_reactions)
    if top_list:
        print(f"\n   🔥 Top Posts by Reactions:")
        for doc in top_list:
            preview = (doc.get("title_or_post", "")[:45] + "...") if len(doc.get("title_or_post", "")) > 45 else doc.get("title_or_post", "")
            print(f"     • {preview} ({doc.get('total_reactions', 0)} reactions)")
    
    # Date range
    oldest = feedbacks_col.find_one(sort=[("feedback_date", 1)])
    newest = feedbacks_col.find_one(sort=[("feedback_date", -1)])
    if oldest and newest:
        print(f"\n   Date Range:")
        print(f"     • Oldest: {oldest.get('feedback_date', 'N/A')}")
        print(f"     • Newest: {newest.get('feedback_date', 'N/A')}")


def main():
    # Default files to ingest
    if len(sys.argv) > 1:
        json_files = sys.argv[1:]
    else:
        # Auto-detect JSON files in current directory
        json_files = [f for f in os.listdir('.') if f.endswith('.json') 
                      and f != 'cookies.json' 
                      and f != 'package.json'
                      and f != 'package-lock.json']
        if not json_files:
            print("[ERROR] No JSON files found. Usage: python ingest_to_mongo.py <file1.json> [file2.json ...]")
            return
    
    print("==================================================")
    print("[DB] MongoDB Data Ingestion Tool")
    print("==================================================")
    print(f"   Target DB:    {DB_NAME}")
    print(f"   Files:        {', '.join(json_files)}")
    
    try:
        client = connect_to_mongo()
        db = client[DB_NAME]
        
        # Create indexes first
        create_indexes(db)
        
        # Ingest each file
        grand_contents = 0
        grand_feedbacks = 0
        
        for filepath in json_files:
            result = ingest_json_file(db, filepath)
            if result:
                grand_contents += result[0]
                grand_feedbacks += result[1]
        
        # Show summary
        show_summary(db)
        
        print(f"\n✅ [SUCCESS] Ingestion complete! "
              f"{grand_contents} contents + {grand_feedbacks} feedbacks processed.")
        print("[NOTE] Posts with status 'final' are permanently retained for analytics.")
        
        client.close()
        
    except Exception as e:
        print(f"\n[ERROR] Failed to connect/ingest: {str(e)}")
        print("[HINT] Make sure MongoDB container is running: docker-compose up -d")


if __name__ == "__main__":
    main()
