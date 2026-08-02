import assert from "node:assert/strict"
import test from "node:test"

import { detectScrapeUrl, splitSseBuffer } from "./scrape-helpers.ts"

test("auto-detects Facebook and Foodpanda targets", () => {
  assert.deepEqual(
    detectScrapeUrl("https://www.facebook.com/LotteriaMyanmar"),
    { source: "facebook", name: "LotteriaMyanmar" }
  )
  assert.deepEqual(
    detectScrapeUrl(
      "https://www.foodpanda.com.mm/restaurant/a1b2/lotteria-junction-city"
    ),
    { source: "foodpanda", name: "Lotteria Junction City" }
  )
  assert.equal(detectScrapeUrl("https://example.com/shop").source, null)
  assert.equal(detectScrapeUrl("http://facebook.com/example").source, null)
  assert.equal(
    detectScrapeUrl(
      "https://www.foodpanda.com.mm/restaurant/abcd1234-lotteria-junction-city"
    ).source,
    null
  )
})

test("SSE parser retains fragmented events and handles CRLF", () => {
  const first = splitSseBuffer('data: {"status":"running"}\r\n\r\ndata: {"stat')
  assert.deepEqual(first.data, ['{"status":"running"}'])
  assert.equal(first.remainder, 'data: {"stat')

  const second = splitSseBuffer(`${first.remainder}us":"completed"}\n\n`)
  assert.deepEqual(second.data, ['{"status":"completed"}'])
  assert.equal(second.remainder, "")
})
