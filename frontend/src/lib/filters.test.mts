import assert from "node:assert/strict"
import test from "node:test"

import { filtersFromSearchParams } from "./stores/filters.ts"

test("URL filters clamp days and discard unknown aspects", () => {
  const highDays = filtersFromSearchParams(
    new URLSearchParams("days=9999&aspect=not-a-real-aspect&entity=-4")
  )
  assert.deepEqual(highDays, { entityId: null, days: 365, aspect: null })

  const valid = filtersFromSearchParams(
    new URLSearchParams("days=7&aspect=staff_and_service&entity=26")
  )
  assert.deepEqual(valid, {
    entityId: 26,
    days: 7,
    aspect: "staff_and_service",
  })
})
