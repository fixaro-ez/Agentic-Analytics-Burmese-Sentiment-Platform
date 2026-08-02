import assert from "node:assert/strict"
import test from "node:test"

import {
  buildForceGraph,
  convexHull,
  formatMiningMetric,
} from "./mining-visuals.ts"
import type { AssociationRule, EntityClusterMember } from "./types.ts"

const rules: AssociationRule[] = [
  {
    antecedent: ["customer_support"],
    consequent: ["fulfillment_and_speed"],
    support: 0.4,
    confidence: 0.8,
    lift: 1.3,
  },
  {
    antecedent: ["fulfillment_and_speed"],
    consequent: ["price_and_value"],
    support: 0.3,
    confidence: 0.6,
    lift: 1.1,
  },
]

test("force graph layout is deterministic and stays inside the canvas", () => {
  const first = buildForceGraph(rules, 600, 360)
  const second = buildForceGraph(rules, 600, 360)

  assert.deepEqual(first, second)
  assert.equal(first.edges.length, 2)
  assert.equal(first.nodes.length, 3)
  for (const node of first.nodes) {
    assert.ok(node.x >= 0 && node.x <= 600)
    assert.ok(node.y >= 0 && node.y <= 360)
  }
})

test("convex hull excludes interior points", () => {
  const entity = (entityId: number): EntityClusterMember => ({
    entity_id: entityId,
    entity_name: `Entity ${entityId}`,
    platform: "test",
    total_reviews: 10,
    positive_ratio: 0.5,
    negative_ratio: 0.3,
    avg_confidence: 0.8,
  })
  const hull = convexHull([
    { x: 0, y: 0, entity: entity(1) },
    { x: 10, y: 0, entity: entity(2) },
    { x: 10, y: 10, entity: entity(3) },
    { x: 0, y: 10, entity: entity(4) },
    { x: 5, y: 5, entity: entity(5) },
  ])

  assert.equal(hull.length, 4)
  assert.ok(!hull.some((point) => point.entity.entity_id === 5))
})

test("metric formatting distinguishes ratios from review volume", () => {
  assert.equal(formatMiningMetric(0.625, "positive_ratio"), "62.5%")
  assert.equal(formatMiningMetric(1234.4, "total_reviews"), "1,234")
})
