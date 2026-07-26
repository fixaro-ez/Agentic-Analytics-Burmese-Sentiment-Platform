"""
In-memory data structure and JSON export for the scraping session.

This module is the source-of-truth for the legacy in-memory `session_data` list
that some scrapers (Foodpanda, blog) populate before flushing to MongoDB.
Facebook scraping writes to MongoDB directly and does not use this module.
"""

from __future__ import annotations

import json
from datetime import datetime

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
