-- Apply to an existing installation before using brand benchmark/impact APIs.
-- The statements are additive and preserve existing entity and analytics APIs.
CREATE TABLE IF NOT EXISTS dim_brands (
    brand_id SERIAL PRIMARY KEY,
    brand_name VARCHAR(255) NOT NULL UNIQUE,
    facebook_entity_id INT NOT NULL UNIQUE REFERENCES dim_entities(entity_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bridge_brand_foodpanda_shops (
    brand_id INT NOT NULL REFERENCES dim_brands(brand_id) ON DELETE CASCADE,
    entity_id INT NOT NULL UNIQUE REFERENCES dim_entities(entity_id),
    PRIMARY KEY (brand_id, entity_id)
);

CREATE TABLE IF NOT EXISTS fact_social_post_classifications (
    post_id VARCHAR(100) PRIMARY KEY
        REFERENCES fact_social_posts(post_id) ON DELETE CASCADE,
    classification VARCHAR(20) NOT NULL CHECK (
        classification IN ('promotional', 'campaign', 'ordinary')
    ),
    confidence DECIMAL(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    review_status VARCHAR(20) NOT NULL CHECK (
        review_status IN (
            'auto_confirmed', 'needs_review', 'analyst_confirmed', 'overridden'
        )
    ),
    source VARCHAR(30) NOT NULL DEFAULT 'rules_v1',
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS brand_foodpanda_brand_idx
    ON bridge_brand_foodpanda_shops (brand_id);
CREATE INDEX IF NOT EXISTS post_classification_status_type_idx
    ON fact_social_post_classifications (review_status, classification);
