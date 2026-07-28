-- ==========================================
-- ABSA Analytics — PostgreSQL Views
-- ==========================================
-- Run this in Supabase SQL Editor or psql
-- AFTER running init_db.sql to create tables.
--
-- These views power the analytics API endpoints.
-- Keep column names aligned with:
--   backend/app/models/analytics.py
--   backend/app/services/analytics.py

-- 1. Per-entity sentiment overview
--    Used by: GET /api/analytics/entities
--    Source: fact_review_absa_results JOIN dim_entities
CREATE OR REPLACE VIEW v_entity_sentiment_overview AS
SELECT
    de.entity_id,
    de.entity_name,
    de.platform,
    COUNT(*) AS total_reviews,
    COUNT(CASE WHEN fra.sentiment_label = 'Positive' THEN 1 END) AS positive_count,
    COUNT(CASE WHEN fra.sentiment_label = 'Negative' THEN 1 END) AS negative_count,
    COUNT(CASE WHEN fra.sentiment_label = 'Neutral' THEN 1 END) AS neutral_count,
    ROUND(
        COUNT(CASE WHEN fra.sentiment_label = 'Positive' THEN 1 END)::NUMERIC
        / NULLIF(COUNT(*), 0),
        4
    ) AS positive_ratio,
    ROUND(
        COUNT(CASE WHEN fra.sentiment_label = 'Negative' THEN 1 END)::NUMERIC
        / NULLIF(COUNT(*), 0),
        4
    ) AS negative_ratio,
    ROUND(AVG(fra.confidence_score), 4) AS avg_confidence
FROM fact_review_absa_results fra
JOIN dim_entities de ON fra.entity_id = de.entity_id
GROUP BY de.entity_id, de.entity_name, de.platform;

-- 2. Aspect × sentiment breakdown
--    Used by: GET /api/analytics/aspects
--    Source: fact_review_absa_results (no join needed)
CREATE OR REPLACE VIEW v_aspect_breakdown AS
SELECT
    fra.aspect_category,
    fra.sentiment_label,
    COUNT(*) AS count,
    ROUND(AVG(fra.confidence_score), 4) AS avg_confidence
FROM fact_review_absa_results fra
WHERE fra.aspect_category != 'no_aspect'
GROUP BY fra.aspect_category, fra.sentiment_label;

-- 3. Daily sentiment trends (per entity)
--    Used by: GET /api/analytics/trends
--    Source: fact_review_absa_results JOIN dim_entities, grouped by date
CREATE OR REPLACE VIEW v_sentiment_daily_trends AS
SELECT
    DATE(fra.feedback_timestamp) AS feedback_date,
    de.entity_id,
    de.entity_name,
    de.platform,
    COUNT(*) AS total_reviews,
    COUNT(CASE WHEN fra.sentiment_label = 'Positive' THEN 1 END) AS positive_count,
    COUNT(CASE WHEN fra.sentiment_label = 'Negative' THEN 1 END) AS negative_count,
    COUNT(CASE WHEN fra.sentiment_label = 'Neutral' THEN 1 END) AS neutral_count,
    ROUND(
        COUNT(CASE WHEN fra.sentiment_label = 'Positive' THEN 1 END)::NUMERIC
        / NULLIF(COUNT(*), 0),
        4
    ) AS positive_ratio
FROM fact_review_absa_results fra
JOIN dim_entities de ON fra.entity_id = de.entity_id
WHERE fra.feedback_timestamp IS NOT NULL
GROUP BY DATE(fra.feedback_timestamp), de.entity_id, de.entity_name, de.platform;

-- 4. Facebook engagement per entity
--    Used by: GET /api/analytics/engagement
--    Source: fact_social_posts JOIN dim_entities
CREATE OR REPLACE VIEW v_facebook_engagement AS
SELECT
    de.entity_id,
    de.entity_name,
    COUNT(*) AS total_posts,
    SUM(fsp.total_reactions) AS total_reactions,
    SUM(fsp.shares_count) AS total_shares,
    SUM(fsp.comments_count) AS total_comments,
    ROUND(AVG(fsp.positivity_ratio), 4) AS avg_positivity_ratio,
    ROUND(AVG(fsp.negativity_ratio), 4) AS avg_negativity_ratio
FROM fact_social_posts fsp
JOIN dim_entities de ON fsp.entity_id = de.entity_id
GROUP BY de.entity_id, de.entity_name;

-- 5. Entity × aspect summary (for data mining)
--    Used by: data mining algorithms (future)
--    Source: fact_review_absa_results JOIN dim_entities
CREATE OR REPLACE VIEW v_entity_aspect_summary AS
SELECT
    de.entity_id,
    de.entity_name,
    de.platform,
    fra.aspect_category,
    fra.sentiment_label,
    COUNT(*) AS count
FROM fact_review_absa_results fra
JOIN dim_entities de ON fra.entity_id = de.entity_id
WHERE fra.aspect_category != 'no_aspect'
GROUP BY de.entity_id, de.entity_name, de.platform, fra.aspect_category, fra.sentiment_label;
