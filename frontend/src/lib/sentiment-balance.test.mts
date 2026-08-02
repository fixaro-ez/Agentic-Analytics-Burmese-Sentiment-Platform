import assert from "node:assert/strict"
import test from "node:test"

import { aggregateSentimentByWeek } from "./sentiment-balance.ts"
import type { SentimentTrendPoint } from "./types.ts"

function point(
  date: string,
  positive: number,
  neutral: number,
  negative: number
): SentimentTrendPoint {
  const total = positive + neutral + negative
  return {
    date,
    entity_id: null,
    entity_name: null,
    total_reviews: total,
    positive_count: positive,
    neutral_count: neutral,
    negative_count: negative,
    positive_ratio: total > 0 ? positive / total : 0,
  }
}

test("aggregates daily sentiment into Monday-based weekly balances", () => {
  const result = aggregateSentimentByWeek([
    point("2026-07-08", 2, 1, 3),
    point("2026-07-06", 1, 0, 2),
    point("2026-07-13", 4, 2, 1),
  ])

  assert.equal(result.length, 2)
  assert.deepEqual(result[0], {
    weekStart: "2026-07-06",
    weekEnd: "2026-07-12",
    weekLabel: "Jul 6",
    weekRange: "Jul 6–Jul 12",
    positiveCount: 3,
    neutralCount: 1,
    negativeCount: 5,
    negativeValue: -5,
    aboveTotal: 4,
    totalReviews: 9,
  })
  assert.equal(result[1].weekStart, "2026-07-13")
  assert.equal(result[1].totalReviews, 7)
})
