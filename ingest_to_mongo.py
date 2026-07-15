"""
MongoDB Data Ingestion Script
──────────────────────────────
Scraped JSON files (facebook_data.json, etc.) ကို MongoDB container ထဲသို့ ingest လုပ်ပေးသည်။

MongoDB Schema Design:
  Database: feedback_analytics
  Collections:
    - contents     → Posts/Reviews/Articles (parent documents)
    - feedbacks    → Comments/Reviews (child documents, linked by content_id)

Usage:
  python ingest_to_mongo.py                          # Default: facebook_data.json
  python ingest_to_mongo.py my_data.json             # Custom file
  python ingest_to_mongo.py file1.json file2.json    # Multiple files
"""

import json
import sys
import os
from datetime import datetime
from pymongo import MongoClient, UpdateOne

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
    JSON ဖိုင်တစ်ခုကို ဖတ်ပြီး MongoDB သို့ ingest လုပ်ခြင်း
    
    Schema:
      contents collection:
        {
          _id: source_content_id,
          source_type: "Social",
          entity_name: "KFC Myanmar",
          title_or_post: "...",
          post_timestamp: ISODate(...),
          scraped_at: ISODate(...),
          comment_count: 9
        }
      
      feedbacks collection:
        {
          _id: feedback_id (fb_comm_...),
          content_id: source_content_id (foreign key),
          entity_name: "KFC Myanmar",
          author: "Zin Nyein Aung",
          raw_text: "...",
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
    
    for item in data:
        source_content_id = item.get("source_content_id", "")
        if not source_content_id:
            continue
        
        # ── Content document (Upsert) ──
        post_ts = parse_timestamp(item.get("post_timestamp", ""))
        
        content_doc = {
            "source_type": item.get("source_type", "Unknown"),
            "entity_name": item.get("entity_name", ""),
            "title_or_post": item.get("title_or_post", ""),
            "post_timestamp": post_ts,
            "scraped_at": now,
            "comment_count": len(item.get("feedbacks", []))
        }
        
        content_ops.append(
            UpdateOne(
                {"_id": source_content_id},
                {"$set": content_doc},
                upsert=True
            )
        )
        total_contents += 1
        
        # ── Feedback documents (Upsert each comment) ──
        for fb in item.get("feedbacks", []):
            feedback_id = fb.get("id", "")
            if not feedback_id:
                continue
            
            fb_ts = parse_timestamp(fb.get("timestamp", ""))
            
            feedback_doc = {
                "content_id": source_content_id,
                "entity_name": item.get("entity_name", ""),
                "source_type": item.get("source_type", "Unknown"),
                "author": fb.get("author", "Unknown"),
                "raw_text": fb.get("text", ""),
                "feedback_date": fb_ts,
                "scraped_at": now
            }
            
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
    
    if not content_ops and not feedback_ops:
        print("   [WARNING] No data to ingest.")
    
    return total_contents, total_feedbacks


def create_indexes(db):
    """Useful indexes for Time-Series analytics and querying"""
    contents_col = db[CONTENTS_COLLECTION]
    feedbacks_col = db[FEEDBACKS_COLLECTION]
    
    # Contents indexes
    contents_col.create_index("entity_name")
    contents_col.create_index("post_timestamp")
    contents_col.create_index("source_type")
    
    # Feedbacks indexes
    feedbacks_col.create_index("content_id")
    feedbacks_col.create_index("entity_name")
    feedbacks_col.create_index("feedback_date")
    feedbacks_col.create_index("author")
    feedbacks_col.create_index([("entity_name", 1), ("feedback_date", -1)])
    
    print("\n[INFO] Indexes created for efficient querying.")


def show_summary(db):
    """Ingestion ပြီးနောက် summary ပြခြင်း"""
    contents_col = db[CONTENTS_COLLECTION]
    feedbacks_col = db[FEEDBACKS_COLLECTION]
    
    print(f"\n{'='*50}")
    print(f"📊 Database Summary: {DB_NAME}")
    print(f"{'='*50}")
    print(f"   Total Contents (Posts/Reviews):  {contents_col.count_documents({})}")
    print(f"   Total Feedbacks (Comments):      {feedbacks_col.count_documents({})}")
    
    # Entity breakdown
    pipeline = [
        {"$group": {"_id": "$entity_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    print(f"\n   By Entity:")
    for doc in feedbacks_col.aggregate(pipeline):
        print(f"     • {doc['_id'] or '(unnamed)'}: {doc['count']} feedbacks")
    
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
        
        client.close()
        
    except Exception as e:
        print(f"\n[ERROR] Failed to connect/ingest: {str(e)}")
        print("[HINT] Make sure MongoDB container is running: docker-compose up -d")


if __name__ == "__main__":
    main()
