-- ==========================================
-- ABSA Analytics — PostgreSQL Star Schema
-- ==========================================
-- Run this in Supabase SQL Editor or psql
-- to create all three tables.

-- 1. Dimension: entities (shops + pages)
CREATE TABLE dim_entities (
    entity_id SERIAL PRIMARY KEY,
    entity_name VARCHAR(255) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    platform_metadata JSONB,
    UNIQUE (entity_name, platform)
);

-- 2. Fact: Facebook posts with ABSA results
CREATE TABLE fact_social_posts (
    post_id VARCHAR(100) PRIMARY KEY,
    entity_id INT REFERENCES dim_entities(entity_id),
    post_timestamp TIMESTAMP,
    post_text TEXT,
    promoted_aspects TEXT[],
    aspect_confidence JSONB,
    total_reactions INT,
    like_count INT,
    love_count INT,
    haha_count INT,
    sad_count INT,
    angry_count INT,
    care_count INT,
    wow_count INT,
    shares_count INT,
    comments_count INT,
    positivity_ratio DECIMAL(5,4),
    negativity_ratio DECIMAL(5,4)
);

-- 3. Fact: review ABSA results (long format)
CREATE TABLE fact_review_absa_results (
    result_id SERIAL PRIMARY KEY,
    feedback_id VARCHAR(100) NOT NULL,
    entity_id INT REFERENCES dim_entities(entity_id),
    feedback_timestamp TIMESTAMP,
    raw_text TEXT,
    aspect_category VARCHAR(100),
    sentiment_label VARCHAR(20),
    confidence_score DECIMAL(5,4)
);
