import assert from "node:assert/strict"
import test from "node:test"

import { paginate } from "./pagination.ts"

test("returns five items per page and a partial final page", () => {
  const entities = Array.from({ length: 8 }, (_, index) => index + 1)

  assert.deepEqual(paginate(entities, 0, 5), {
    items: [1, 2, 3, 4, 5],
    page: 0,
    pageCount: 2,
    rangeStart: 1,
    rangeEnd: 5,
    total: 8,
  })
  assert.deepEqual(paginate(entities, 1, 5), {
    items: [6, 7, 8],
    page: 1,
    pageCount: 2,
    rangeStart: 6,
    rangeEnd: 8,
    total: 8,
  })
})

test("clamps invalid page numbers when data changes", () => {
  const entities = [1, 2, 3]

  assert.equal(paginate(entities, 10, 5).page, 0)
  assert.equal(paginate(entities, -2, 5).page, 0)
  assert.equal(paginate(entities, Number.NaN, 5).page, 0)
})

test("returns an empty range for an empty collection", () => {
  assert.deepEqual(paginate([], 0, 5), {
    items: [],
    page: 0,
    pageCount: 0,
    rangeStart: 0,
    rangeEnd: 0,
    total: 0,
  })
})

test("rejects invalid page sizes", () => {
  assert.throws(() => paginate([1], 0, 0), RangeError)
  assert.throws(() => paginate([1], 0, 2.5), RangeError)
})
