-- Cut over persisted ABSA data from the legacy six-aspect taxonomy to the
-- retrained five-aspect taxonomy. Existing rows are mapped only to keep the
-- database valid during deployment; the full inference/export run immediately
-- after this migration replaces them with predictions from the new models.

BEGIN;

ALTER TABLE fact_review_absa_results
    DROP CONSTRAINT IF EXISTS fact_review_absa_aspect_check;

UPDATE fact_review_absa_results
SET aspect_category = CASE aspect_category
    WHEN 'product_or_service_quality' THEN 'product_quality'
    WHEN 'customer_support' THEN 'staff_and_service'
    ELSE aspect_category
END
WHERE aspect_category IN (
    'product_or_service_quality',
    'customer_support'
);

DELETE FROM fact_review_absa_results
WHERE aspect_category = 'digital_experience';

UPDATE fact_social_posts
SET
    promoted_aspects = CASE
        WHEN promoted_aspects IS NULL THEN NULL
        ELSE ARRAY(
            SELECT DISTINCT CASE aspect
                WHEN 'product_or_service_quality' THEN 'product_quality'
                WHEN 'customer_support' THEN 'staff_and_service'
                ELSE aspect
            END
            FROM unnest(promoted_aspects) AS aspect
            WHERE aspect <> 'digital_experience'
            ORDER BY 1
        )
    END,
    aspect_confidence = CASE
        WHEN aspect_confidence IS NULL THEN NULL
        ELSE
            (
                aspect_confidence
                - 'product_or_service_quality'
                - 'digital_experience'
                - 'customer_support'
            )
            || CASE
                WHEN aspect_confidence ? 'product_or_service_quality'
                THEN jsonb_build_object(
                    'product_quality',
                    aspect_confidence -> 'product_or_service_quality'
                )
                ELSE '{}'::jsonb
            END
            || CASE
                WHEN aspect_confidence ? 'customer_support'
                THEN jsonb_build_object(
                    'staff_and_service',
                    aspect_confidence -> 'customer_support'
                )
                ELSE '{}'::jsonb
            END
    END
WHERE
    promoted_aspects && ARRAY[
        'product_or_service_quality',
        'digital_experience',
        'customer_support'
    ]::text[]
    OR aspect_confidence ?| ARRAY[
        'product_or_service_quality',
        'digital_experience',
        'customer_support'
    ];

ALTER TABLE fact_review_absa_results
    ADD CONSTRAINT fact_review_absa_aspect_check CHECK (
        aspect_category IN (
            'product_quality',
            'fulfillment_and_speed',
            'price_and_value',
            'staff_and_service',
            'variety_and_availability',
            'no_aspect'
        )
    );

COMMIT;
