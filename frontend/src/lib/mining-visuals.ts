import type {
  AssociationRule,
  EntityClusterMember,
  MiningAxis,
} from "@/lib/types"

export interface ForceNode {
  id: string
  x: number
  y: number
  degree: number
}

export interface ForceEdge {
  rule: AssociationRule
  ruleIndex: number
  source: ForceNode
  target: ForceNode
}

export interface ForceGraphLayout {
  nodes: ForceNode[]
  edges: ForceEdge[]
  width: number
  height: number
}

export function buildForceGraph(
  rules: AssociationRule[],
  width = 760,
  height = 420
): ForceGraphLayout {
  const ids = Array.from(
    new Set(
      rules.flatMap((rule) => [
        ...rule.antecedent,
        ...rule.consequent,
      ])
    )
  ).sort()
  const degree = new Map<string, number>()
  for (const rule of rules) {
    const source = rule.antecedent[0]
    const target = rule.consequent[0]
    degree.set(source, (degree.get(source) ?? 0) + 1)
    degree.set(target, (degree.get(target) ?? 0) + 1)
  }

  const radius = Math.min(width, height) * 0.34
  const nodes = ids.map((id, index) => {
    const angle = (index / Math.max(ids.length, 1)) * Math.PI * 2 - Math.PI / 2
    return {
      id,
      x: width / 2 + Math.cos(angle) * radius,
      y: height / 2 + Math.sin(angle) * radius,
      degree: degree.get(id) ?? 0,
      vx: 0,
      vy: 0,
    }
  })
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const edgePairs = rules
    .map((rule, ruleIndex) => ({
      rule,
      ruleIndex,
      source: nodeById.get(rule.antecedent[0]),
      target: nodeById.get(rule.consequent[0]),
    }))
    .filter(
      (
        edge
      ): edge is {
        rule: AssociationRule
        ruleIndex: number
        source: (typeof nodes)[number]
        target: (typeof nodes)[number]
      } => Boolean(edge.source && edge.target)
    )

  for (let iteration = 0; iteration < 100; iteration += 1) {
    for (let left = 0; left < nodes.length; left += 1) {
      for (let right = left + 1; right < nodes.length; right += 1) {
        const a = nodes[left]
        const b = nodes[right]
        const dx = b.x - a.x || 0.01
        const dy = b.y - a.y || 0.01
        const distanceSquared = Math.max(dx * dx + dy * dy, 64)
        const force = 3400 / distanceSquared
        const distanceValue = Math.sqrt(distanceSquared)
        const fx = (dx / distanceValue) * force
        const fy = (dy / distanceValue) * force
        a.vx -= fx
        a.vy -= fy
        b.vx += fx
        b.vy += fy
      }
    }

    for (const edge of edgePairs) {
      const dx = edge.target.x - edge.source.x
      const dy = edge.target.y - edge.source.y
      const distanceValue = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const targetDistance = 115 + (1 - edge.rule.confidence) * 55
      const spring = (distanceValue - targetDistance) * 0.012
      const fx = (dx / distanceValue) * spring
      const fy = (dy / distanceValue) * spring
      edge.source.vx += fx
      edge.source.vy += fy
      edge.target.vx -= fx
      edge.target.vy -= fy
    }

    for (const node of nodes) {
      node.vx += (width / 2 - node.x) * 0.004
      node.vy += (height / 2 - node.y) * 0.004
      node.vx *= 0.74
      node.vy *= 0.74
      node.x = Math.min(width - 76, Math.max(76, node.x + node.vx))
      node.y = Math.min(height - 52, Math.max(52, node.y + node.vy))
    }
  }

  return {
    nodes: nodes.map(({ id, x, y, degree: nodeDegree }) => ({
      id,
      x,
      y,
      degree: nodeDegree,
    })),
    edges: edgePairs.map((edge) => ({
      rule: edge.rule,
      ruleIndex: edge.ruleIndex,
      source: {
        id: edge.source.id,
        x: edge.source.x,
        y: edge.source.y,
        degree: edge.source.degree,
      },
      target: {
        id: edge.target.id,
        x: edge.target.x,
        y: edge.target.y,
        degree: edge.target.degree,
      },
    })),
    width,
    height,
  }
}

export interface PlotPoint {
  x: number
  y: number
  entity: EntityClusterMember
}

function cross(origin: PlotPoint, a: PlotPoint, b: PlotPoint) {
  return (
    (a.x - origin.x) * (b.y - origin.y) -
    (a.y - origin.y) * (b.x - origin.x)
  )
}

export function convexHull(points: PlotPoint[]): PlotPoint[] {
  if (points.length < 3) return []
  const sorted = [...points].sort(
    (a, b) => a.x - b.x || a.y - b.y || a.entity.entity_id - b.entity.entity_id
  )
  const lower: PlotPoint[] = []
  for (const point of sorted) {
    while (
      lower.length >= 2 &&
      cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0
    ) {
      lower.pop()
    }
    lower.push(point)
  }
  const upper: PlotPoint[] = []
  for (const point of [...sorted].reverse()) {
    while (
      upper.length >= 2 &&
      cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0
    ) {
      upper.pop()
    }
    upper.push(point)
  }
  lower.pop()
  upper.pop()
  return [...lower, ...upper]
}

export const MINING_AXIS_LABELS: Record<MiningAxis, string> = {
  positive_ratio: "Positive ratio",
  negative_ratio: "Negative ratio",
  avg_confidence: "Model confidence",
  total_reviews: "Review volume",
}

export function miningMetricValue(
  entity: EntityClusterMember,
  axis: MiningAxis
) {
  return Number(entity[axis] ?? 0)
}

export function formatMiningMetric(value: number, axis: MiningAxis) {
  return axis === "total_reviews"
    ? Math.round(value).toLocaleString()
    : `${(value * 100).toFixed(1)}%`
}
