import assert from "node:assert/strict"
import test from "node:test"

import { buildAspectSentimentRows } from "./aspect-sentiment.ts"
import type { AspectBreakdown } from "./types.ts"

const data: AspectBreakdown[] = [
  {
    aspect: "price_and_value",
    sentiment: "Positive",
    count: 3,
    percentage: 0.3,
  },
  {
    aspect: "price_and_value",
    sentiment: "Neutral",
    count: 2,
    percentage: 0.2,
  },
  {
    aspect: "price_and_value",
    sentiment: "Negative",
    count: 5,
    percentage: 0.5,
  },
  {
    aspect: "customer_support",
    sentiment: "Positive",
    count: 1,
    percentage: 0.2,
  },
  {
    aspect: "customer_support",
    sentiment: "Negative",
    count: 4,
    percentage: 0.8,
  },
]

test("normalizes each aspect to 100 percent while preserving volume", () => {
  const rows = buildAspectSentimentRows(data)

  assert.equal(rows[0].aspect, "price_and_value")
  assert.equal(rows[0].total, 10)
  assert.equal(rows[0].positiveShare, 30)
  assert.equal(rows[0].neutralShare, 20)
  assert.equal(rows[0].negativeShare, 50)
  assert.equal(
    rows[0].positiveShare + rows[0].neutralShare + rows[0].negativeShare,
    100
  )
})

test("sorts by negative share instead of raw negative count", () => {
  const rows = buildAspectSentimentRows(data, "negativity")

  assert.equal(rows[0].aspect, "customer_support")
  assert.equal(rows[0].negativeShare, 80)
})
