import assert from "node:assert/strict"
import test from "node:test"

import { benchmarkResponseState } from "./benchmark-helpers.ts"
import type { BenchmarkResponse } from "./types.ts"

test("benchmark response handling distinguishes guarded and partial data", () => {
  const base = {
    aspects: [],
    insights: [],
    meta: {
      filters: {
        brands: [
          { brand_id: 1, foodpanda_entity_ids: [11] },
          { brand_id: 2, foodpanda_entity_ids: [22] },
        ],
        days: 30,
      },
      minimum_reviews: 30,
      delta_threshold: 0.1,
      sufficient_data: true,
      eligible_brand_count: 2,
      channel_shares_available: true,
      assumptions: [],
    },
  }
  const brand = {
    brand_id: 1,
    brand_name: "One",
    facebook_entity_id: 10,
    foodpanda_entity_ids: [11],
    review_count: 40,
    eligible: true,
    facebook_post_count: 5,
    facebook_weighted_engagement: 100,
    facebook_share: 0.5,
    foodpanda_share: 0.5,
    combined_share_of_voice: 0.5,
    net_sentiment: 0.2,
    warning: null,
  }

  assert.equal(
    benchmarkResponseState({
      ...base,
      brands: [brand, { ...brand, brand_id: 2 }],
    } as BenchmarkResponse),
    "ready"
  )
  assert.equal(
    benchmarkResponseState({
      ...base,
      brands: [
        brand,
        {
          ...brand,
          brand_id: 2,
          eligible: false,
          net_sentiment: null,
          review_count: 5,
        },
      ],
      meta: { ...base.meta, eligible_brand_count: 1, sufficient_data: false },
    } as BenchmarkResponse),
    "partial"
  )
  assert.equal(
    benchmarkResponseState({
      ...base,
      brands: [{ ...brand, eligible: false }],
      meta: { ...base.meta, eligible_brand_count: 0, sufficient_data: false },
    } as BenchmarkResponse),
    "insufficient"
  )
})
