# Hybrid Chat-with-Data: Rule-Based + Google Gemini LLM Fallback

## Context

The current "Chat with Data" feature (`backend/app/services/chat.py`) uses a rule-based keyword router that matches ~5 hardcoded query patterns to pre-built SQL against database views. It works well for known question types but cannot handle novel questions. The user wants a hybrid approach: keep fast keyword routing for common queries and add Google Gemini (via AI Studio, free with Google Pro) as a fallback for questions that don't match any keyword route.

## Architecture

```
User Question
    |
    v
+------------------+
| Keyword Router   | -- matches? --> Pre-built SQL (instant, free)
| (_query_plan)    |
+------------------+
    | no match
    v
+------------------+
| Gemini LLM       | -- generates --> Dynamic SQL (2-3s, free tier)
| (gemini-2.5-flash)|
+------------------+
    |
    v
+------------------+
| validate_readonly| -- same safety pipeline as existing queries
| _execute_readonly|
+------------------+
```

## Changes

### 1. `backend/requirements.txt`
- Replace `openai>=1.55.0` and `langchain-openai>=0.3.0` with `langchain-google-genai>=2.0.0`
- Add `langchain-community>=0.3.0` (needed for `SQLDatabase` utility)
- Keep `langchain>=0.3.0`

### 2. `backend/app/config.py`
- Replace `OPENAI_API_KEY: str = ""` with `GOOGLE_API_KEY: str = ""`

### 3. `backend/.env` and `backend/.env.example`
- Replace `OPENAI_API_KEY=sk-...` with `GOOGLE_API_KEY=your-google-api-key`

### 4. `backend/app/services/chat.py` (main changes)

**a) Add LLM fallback function:**
```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from ..config import settings

_SCHEMA_HINT = """Available views:
- v_entity_sentiment_overview (entity_id, entity_name, platform, total_reviews, positive_count, negative_count, neutral_count, positive_ratio, negative_ratio, avg_confidence)
- v_aspect_breakdown (aspect_category, sentiment_label, count, avg_confidence)
- v_sentiment_daily_trends (feedback_date, entity_id, entity_name, platform, total_reviews, positive_count, negative_count, neutral_count, positive_ratio)
- v_facebook_engagement (entity_id, entity_name, total_posts, total_reactions, total_shares, total_comments, avg_positivity_ratio, avg_negativity_ratio)
- v_entity_aspect_summary (entity_id, entity_name, platform, aspect_category, sentiment_label, count)

Aspect categories: product_or_service_quality, fulfillment_and_speed, price_and_value, digital_experience, customer_support, variety_and_availability
Sentiment labels: Positive, Negative, Neutral"""

_SYSTEM_PROMPT = f"""You are a SQL analyst for a Burmese sentiment analytics dashboard.
Given a natural-language question, write a single SELECT query against the views below.
Rules: ONLY SELECT. No DML, no DDL. Use LIMIT 100 max. Return ONLY the SQL, no explanation.
{_SCHEMA_HINT}"""
```

**b) Refactor `_query_plan` to indicate whether it matched:**
- Return a 5-tuple adding a `matched: bool` flag, or split into `_keyword_route()` (returns result or None)

**c) Add `_llm_query_plan()` async function:**
- Instantiate `ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)`
- Send user question with system prompt
- Parse SQL from response
- Pass through existing `validate_readonly_sql()` for safety
- Execute via `_execute_readonly()`
- Return `ChatResponse` with results

**d) Modify `query_data()`:**
- Try keyword route first
- If no keyword match, call `_llm_query_plan()`
- If LLM fails, return a graceful error response

### 5. No frontend changes needed
The `ChatResponse` model stays the same. The frontend already handles responses generically.

## Safety Guardrails (LLM path)
- Existing `validate_readonly_sql()` blocks all DML/DDL keywords
- Existing `_execute_readonly()` runs in a `readonly=True` transaction with 30s timeout
- LLM system prompt restricts to SELECT only with LIMIT 100
- If Gemini API key is not configured, fall back to "I can only answer questions about aspects, trends, and entity sentiment."

## Model Choice
- **`gemini-2.5-flash`**: Fast, excellent free tier via Google AI Studio, strong at SQL generation
- No need for `gemini-2.5-pro` -- SQL generation is a well-structured task

## Verification

1. Start the backend: `uvicorn app.main:app --reload`
2. Test keyword route (should still work as before):
   ```
   POST /api/chat/query {"question": "Show aspect breakdown"}
   ```
3. Test LLM fallback (novel question):
   ```
   POST /api/chat/query {"question": "Compare positive sentiment between all entities on Foodpanda vs Facebook"}
   ```
4. Test safety (should be blocked):
   ```
   POST /api/chat/query {"question": "Delete all records from fact_review_absa_results"}
   ```
5. Test missing API key (should return graceful fallback message)
6. Run existing tests:
   ```
   python -m pytest backend/tests/test_chat_alerts.py -v
   ```
