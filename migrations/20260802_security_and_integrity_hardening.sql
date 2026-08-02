-- Close default Supabase Data API grants and enforce analytics invariants.
-- Safe to apply repeatedly after init_db.sql and the earlier migrations.

BEGIN;

ALTER TABLE dim_brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE bridge_brand_foodpanda_shops ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_social_post_classifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS dim_brands_authenticated_read ON dim_brands;
CREATE POLICY dim_brands_authenticated_read ON dim_brands
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS brand_shops_authenticated_read ON bridge_brand_foodpanda_shops;
CREATE POLICY brand_shops_authenticated_read ON bridge_brand_foodpanda_shops
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS post_classifications_authenticated_read
    ON fact_social_post_classifications;
CREATE POLICY post_classifications_authenticated_read
    ON fact_social_post_classifications
    FOR SELECT TO authenticated USING (true);

REVOKE ALL PRIVILEGES ON TABLE
    dim_entities,
    dim_brands,
    bridge_brand_foodpanda_shops,
    fact_social_posts,
    fact_social_post_classifications,
    fact_review_absa_results,
    etl_runs,
    scrape_entities,
    scrape_runs,
    scrape_schedules
FROM anon;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE
    dim_entities,
    dim_brands,
    bridge_brand_foodpanda_shops,
    fact_social_posts,
    fact_social_post_classifications,
    fact_review_absa_results,
    etl_runs
FROM authenticated;

GRANT SELECT ON TABLE
    dim_entities,
    dim_brands,
    bridge_brand_foodpanda_shops,
    fact_social_posts,
    fact_social_post_classifications,
    fact_review_absa_results,
    etl_runs
TO authenticated;

REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon;

ALTER TABLE dim_entities
    DROP CONSTRAINT IF EXISTS dim_entities_platform_check;
ALTER TABLE dim_entities
    ADD CONSTRAINT dim_entities_platform_check
    CHECK (platform IN ('facebook', 'foodpanda'));

ALTER TABLE fact_review_absa_results
    ALTER COLUMN entity_id SET NOT NULL;
ALTER TABLE fact_review_absa_results
    DROP CONSTRAINT IF EXISTS fact_review_absa_aspect_check,
    DROP CONSTRAINT IF EXISTS fact_review_absa_sentiment_check,
    DROP CONSTRAINT IF EXISTS fact_review_absa_confidence_check,
    DROP CONSTRAINT IF EXISTS fact_review_absa_no_aspect_check;
ALTER TABLE fact_review_absa_results
    ADD CONSTRAINT fact_review_absa_aspect_check CHECK (
        aspect_category IN (
            'product_or_service_quality',
            'fulfillment_and_speed',
            'price_and_value',
            'digital_experience',
            'customer_support',
            'variety_and_availability',
            'no_aspect'
        )
    ),
    ADD CONSTRAINT fact_review_absa_sentiment_check CHECK (
        sentiment_label IS NULL OR sentiment_label IN ('Positive', 'Negative', 'Neutral')
    ),
    ADD CONSTRAINT fact_review_absa_confidence_check CHECK (
        confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1
    ),
    ADD CONSTRAINT fact_review_absa_no_aspect_check CHECK (
        (aspect_category = 'no_aspect') = (sentiment_label IS NULL)
    );

ALTER TABLE fact_social_posts
    ALTER COLUMN entity_id SET NOT NULL;
ALTER TABLE fact_social_posts
    DROP CONSTRAINT IF EXISTS fact_social_posts_counts_check,
    DROP CONSTRAINT IF EXISTS fact_social_posts_ratios_check;
ALTER TABLE fact_social_posts
    ADD CONSTRAINT fact_social_posts_counts_check CHECK (
        (total_reactions IS NULL OR total_reactions >= 0)
        AND (like_count IS NULL OR like_count >= 0)
        AND (love_count IS NULL OR love_count >= 0)
        AND (haha_count IS NULL OR haha_count >= 0)
        AND (sad_count IS NULL OR sad_count >= 0)
        AND (angry_count IS NULL OR angry_count >= 0)
        AND (care_count IS NULL OR care_count >= 0)
        AND (wow_count IS NULL OR wow_count >= 0)
        AND (shares_count IS NULL OR shares_count >= 0)
        AND (comments_count IS NULL OR comments_count >= 0)
    ),
    ADD CONSTRAINT fact_social_posts_ratios_check CHECK (
        (positivity_ratio IS NULL OR positivity_ratio BETWEEN 0 AND 1)
        AND (negativity_ratio IS NULL OR negativity_ratio BETWEEN 0 AND 1)
    );

DO $$
DECLARE
    view_name TEXT;
BEGIN
    FOREACH view_name IN ARRAY ARRAY[
        'v_entity_sentiment_overview',
        'v_aspect_breakdown',
        'v_sentiment_daily_trends',
        'v_facebook_engagement',
        'v_entity_aspect_summary'
    ] LOOP
        IF to_regclass('public.' || view_name) IS NOT NULL THEN
            EXECUTE format(
                'ALTER VIEW public.%I SET (security_invoker = true)', view_name
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated',
                view_name
            );
            EXECUTE format(
                'GRANT SELECT ON TABLE public.%I TO authenticated', view_name
            );
        END IF;
    END LOOP;
END;
$$;

COMMIT;
