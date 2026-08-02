-- Keep UI "review" metrics at one row per source review. The ABSA fact table
-- is intentionally long-format, so counting its rows inflates review volume
-- whenever one review contains multiple aspects.

CREATE OR REPLACE VIEW v_entity_sentiment_overview
WITH (security_invoker = true) AS
WITH ranked_reviews AS (
    SELECT
        fra.*,
        ROW_NUMBER() OVER (
            PARTITION BY fra.entity_id, fra.feedback_id
            ORDER BY
                (fra.sentiment_label IS NOT NULL) DESC,
                fra.confidence_score DESC NULLS LAST,
                fra.result_id DESC
        ) AS review_rank
    FROM fact_review_absa_results fra
)
SELECT
    de.entity_id,
    de.entity_name,
    de.platform,
    COUNT(*) AS total_reviews,
    COUNT(*) FILTER (WHERE fra.sentiment_label = 'Positive') AS positive_count,
    COUNT(*) FILTER (WHERE fra.sentiment_label = 'Negative') AS negative_count,
    COUNT(*) FILTER (WHERE fra.sentiment_label = 'Neutral') AS neutral_count,
    ROUND(
        COUNT(*) FILTER (WHERE fra.sentiment_label = 'Positive')::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE fra.sentiment_label IS NOT NULL), 0),
        4
    ) AS positive_ratio,
    ROUND(
        COUNT(*) FILTER (WHERE fra.sentiment_label = 'Negative')::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE fra.sentiment_label IS NOT NULL), 0),
        4
    ) AS negative_ratio,
    ROUND(AVG(fra.confidence_score) FILTER (WHERE fra.sentiment_label IS NOT NULL), 4) AS avg_confidence
FROM ranked_reviews fra
JOIN dim_entities de ON fra.entity_id = de.entity_id
WHERE fra.review_rank = 1
GROUP BY de.entity_id, de.entity_name, de.platform;

CREATE OR REPLACE VIEW v_sentiment_daily_trends
WITH (security_invoker = true) AS
WITH ranked_reviews AS (
    SELECT
        fra.*,
        ROW_NUMBER() OVER (
            PARTITION BY fra.entity_id, fra.feedback_id
            ORDER BY
                (fra.sentiment_label IS NOT NULL) DESC,
                fra.confidence_score DESC NULLS LAST,
                fra.result_id DESC
        ) AS review_rank
    FROM fact_review_absa_results fra
)
SELECT
    DATE(fra.feedback_timestamp) AS feedback_date,
    de.entity_id,
    de.entity_name,
    de.platform,
    COUNT(*) AS total_reviews,
    COUNT(*) FILTER (WHERE fra.sentiment_label = 'Positive') AS positive_count,
    COUNT(*) FILTER (WHERE fra.sentiment_label = 'Negative') AS negative_count,
    COUNT(*) FILTER (WHERE fra.sentiment_label = 'Neutral') AS neutral_count,
    ROUND(
        COUNT(*) FILTER (WHERE fra.sentiment_label = 'Positive')::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE fra.sentiment_label IS NOT NULL), 0),
        4
    ) AS positive_ratio
FROM ranked_reviews fra
JOIN dim_entities de ON fra.entity_id = de.entity_id
WHERE fra.review_rank = 1
  AND fra.feedback_timestamp IS NOT NULL
GROUP BY DATE(fra.feedback_timestamp), de.entity_id, de.entity_name, de.platform;

REVOKE ALL ON v_entity_sentiment_overview, v_sentiment_daily_trends FROM anon;
GRANT SELECT ON v_entity_sentiment_overview, v_sentiment_daily_trends TO authenticated;
