# Fix Duplicate Entities & Burmese Prefix Issue

## Context

The dashboard shows two "The Pizza Company (South Oakkala)" entries because the Foodpanda scraper failed to strip the Burmese prefix `ဝေဖန်သုံးသပ်ချက်များ` from the page title, creating a second entity in both MongoDB and PostgreSQL. This plan cleans up the duplicate data and prevents future occurrences.

## Current State

- **PostgreSQL `dim_entities`**: entity_id=1 (`The Pizza Company (South Oakkala)`) and entity_id=4 (`ဝေဖန်သုံးသပ်ချက်များ The Pizza Company (South Oakkala)`)
- **PostgreSQL `fact_review_absa_results`**: 48 rows reference entity_id=4 (the duplicate)
- **MongoDB `contents`**: 1 doc with Burmese prefix
- **MongoDB `feedbacks`**: 42 docs with Burmese prefix
- **MongoDB `cleaned_contents`**: 1 doc with Burmese prefix
- **MongoDB `cleaned_feedbacks`**: 42 docs with Burmese prefix

## Plan

### Phase 1: Data Cleanup

#### 1.1 MongoDB — Strip Burmese prefix from `entity_name`
Run `updateMany` on all 4 collections in `feedback_analytics`:

```
Filter: { entity_name: "ဝေဖန်သုံးသပ်ချက်များ The Pizza Company (South Oakkala)" }
Update: { $set: { entity_name: "The Pizza Company (South Oakkala)" } }
```

Also update `title_or_post` in `contents` and `cleaned_contents` where it contains the prefix.

#### 1.2 PostgreSQL — Merge duplicate entity
```sql
UPDATE fact_review_absa_results SET entity_id = 1 WHERE entity_id = 4;
DELETE FROM dim_entities WHERE entity_id = 4;
```

### Phase 2: Code Fixes

#### 2.1 Fix Foodpanda entity name regex
**File:** `src/burmese_absa/scraping/foodpanda.py:619-623`

The current regex `^(?:ဝေဖန်\s*)?သုံးသပ်ချက်(?:များ)?\s*` fails when there is no space between `ဝေဖန်` and `သုံးသပ်ချက်`. Fix:

```python
r'^(?:ဝေဖန်\s*သုံးသပ်ချက်(?:များ)?|သုံးသပ်ချက်(?:များ)?|အဆင့်သတ်မှတ်ချက်(?:များ)?|Reviews?)\s*'
```

#### 2.2 Normalize entity names in ETL
**File:** `backend/app/services/etl.py:289-292`

Add `_normalize_name()` that trims and collapses whitespace. Apply to both entity set collection and `_get_entity_id` lookup.

#### 2.3 Add entity name autocomplete to scraping form
**File:** `frontend/src/app/(app)/scraping/page.tsx:338-346`

- Fetch existing entities from `GET /api/entities` on mount (endpoint already exists)
- Filter by current platform (`source`)
- Use native `<datalist>` with `<option>` elements for suggestions
- Keep free-text input so new names are still allowed

### Phase 3: Files Changed

| File | Change |
|------|--------|
| `src/burmese_absa/scraping/foodpanda.py` | Fix Burmese prefix regex (line 620) |
| `backend/app/services/etl.py` | Add `_normalize_name()` to entity dedup |
| `frontend/src/app/(app)/scraping/page.tsx` | Add entity name datalist autocomplete |

### Phase 4: Verification
1. MongoDB: verify 0 docs with Burmese prefix in all 4 collections
2. PostgreSQL: `SELECT * FROM dim_entities` shows 1 Pizza Company row
3. Run existing tests: `PYTHONPATH=src python -m unittest tests.test_foodpanda`
4. Frontend: open scraping page, type in entity name field, verify autocomplete suggestions appear
