# Project Database Design (Star Schema)

*PostgreSQL · Aspect-Based Sentiment Analysis (ABSA) Project*

This document outlines the comprehensive PostgreSQL database design for the Aspect-Based Sentiment Analysis (ABSA) project, utilizing a Star Schema architecture. This design accommodates both Foodpanda reviews (with ABSA results) and Facebook engagement metrics.

## 1. Overview

The architecture consists of one central dimension table and two fact tables. The dimension table stores entity information (shops/pages), and the fact tables store transactional/event data (reviews and social posts). They are linked via a one-to-many relationship.

## 2. Dimension Table: `dim_entities`

This table acts as the central hub, storing metadata for both Foodpanda shops and Facebook pages. It uses a JSONB column to flexibly store platform-specific attributes without requiring sparse columns.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `entity_id` | SERIAL | PRIMARY KEY | Unique auto-generated identifier for the entity. |
| `entity_name` | VARCHAR(255) | NOT NULL | Name of the entity (e.g., "Lotteria Myanmar", "Reviews OMUK (CW)"). |
| `platform` | VARCHAR(50) | NOT NULL | Platform of the entity (e.g., 'facebook', 'foodpanda'). |
| `platform_metadata` | JSONB | — | Flexible storage for platform-specific data.<br>Foodpanda Ex: `{"source_shop_id": "shop_d00190c6cd63aa35"}`<br>Facebook Ex: `{"page_url": "https://www.facebook.com/LotteriaMyanmar"}` |

**SQL Creation Script**

```sql
CREATE TABLE dim_entities (
    entity_id SERIAL PRIMARY KEY,
    entity_name VARCHAR(255) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    platform_metadata JSONB
);
```

## 3. Fact Table 1: `fact_social_posts`

This table stores engagement metrics scraped from Facebook posts. It links back to the dim_entities table to associate the post with a specific Facebook page.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `post_id` | VARCHAR(100) | PRIMARY KEY | Unique ID from the source (e.g., "fb_post_cd17d2..."). |
| `entity_id` | INT | REFERENCES dim_entities(entity_id) | Foreign key linking to the page in dim_entities. |
| `post_timestamp` | TIMESTAMP | — | Time the post was published. |
| `post_text` | TEXT | — | The full text of the Facebook post. |
| `total_reactions` | INT | — | Total number of reactions. |
| `like_count` | INT | — | Number of 'Like' reactions. |
| `love_count` | INT | — | Number of 'Love' reactions. |
| `haha_count` | INT | — | Number of 'Haha' reactions. |
| `sad_count` | INT | — | Number of 'Sad' reactions. |
| `angry_count` | INT | — | Number of 'Angry' reactions. |
| `care_count` | INT | — | Number of 'Care' reactions. |
| `shares_count` | INT | — | Number of shares. |
| `comments_count` | INT | — | Number of comments. |
| `positivity_ratio` | DECIMAL(5,4) | — | Calculated metric (e.g., 0.1007). |
| `negativity_ratio` | DECIMAL(5,4) | — | Calculated metric. |

**SQL Creation Script**

```sql
CREATE TABLE fact_social_posts (
    post_id VARCHAR(100) PRIMARY KEY,
    entity_id INT REFERENCES dim_entities(entity_id),
    post_timestamp TIMESTAMP,
    post_text TEXT,
    total_reactions INT,
    like_count INT,
    love_count INT,
    haha_count INT,
    sad_count INT,
    angry_count INT,
    care_count INT,
    shares_count INT,
    comments_count INT,
    positivity_ratio DECIMAL(5,4),
    negativity_ratio DECIMAL(5,4)
);
```

## 4. Fact Table 2: `fact_review_absa_results`

This table stores the final output from the two-stage NLP pipeline. It uses a "Long Format" design, meaning a single review may generate multiple rows if multiple aspects are detected.

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| `result_id` | SERIAL | PRIMARY KEY | Unique auto-generated ID for the specific aspect-sentiment result. |
| `feedback_id` | VARCHAR(100) | NOT NULL | ID of the original review (e.g., "fp_rev_274e43b4..."). |
| `entity_id` | INT | REFERENCES dim_entities(entity_id) | Foreign key linking to the shop in dim_entities. |
| `feedback_timestamp` | TIMESTAMP | — | Time the review was posted. |
| `raw_text` | TEXT | — | The original, cleaned review text. |
| `aspect_category` | VARCHAR(100) | — | The aspect detected by Stage 1 (e.g., 'product_or_service_quality'). If no aspect is detected, this will be 'no_aspect'. |
| `sentiment_label` | VARCHAR(20) | — | The sentiment output by Stage 2 ('Positive', 'Negative', 'Neutral'). If aspect is 'no_aspect', this should be 'Neutral' or NULL. |
| `confidence_score` | DECIMAL(5,4) | — | The confidence score from the Stage 2 model (e.g., 0.9850). |

**SQL Creation Script**

```sql
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
```
