"use client"

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from "recharts"
import type { EntitySentimentOverview } from "@/lib/types"

const COLORS = [
  "#6366f1", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6",
  "#ef4444", "#3b82f6", "#22c55e", "#f97316", "#06b6d4",
]

interface EntityRadarProps {
  entities: EntitySentimentOverview[]
  loading?: boolean
}

export function EntityRadar({ entities, loading }: EntityRadarProps) {
  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading entity data...</p>
      </div>
    )
  }

  if (!entities || entities.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">No entity data available</p>
      </div>
    )
  }

  const metrics = [
    { key: "positive_ratio", label: "Positive %" },
    { key: "negative_ratio", label: "Negative %" },
    { key: "total_reviews", label: "Reviews" },
    { key: "avg_confidence", label: "Confidence" },
  ]

  const maxReviews = Math.max(...entities.map((e) => e.total_reviews), 1)

  const chartData = metrics.map((m) => {
    const point: Record<string, string | number> = { metric: m.label }
    entities.forEach((e) => {
      const val = e[m.key as keyof EntitySentimentOverview] as number | null
      if (m.key === "total_reviews") {
        point[e.entity_name] = val ? (val / maxReviews) * 100 : 0
      } else {
        point[e.entity_name] = val ? val * 100 : 0
      }
    })
    return point
  })

  return (
    <div className="h-[26rem] min-w-0 w-full overflow-hidden">
    <ResponsiveContainer
      width="100%"
      height="100%"
      minWidth={0}
      initialDimension={{ width: 900, height: 416 }}
    >
      <RadarChart data={chartData} outerRadius="72%" role="img" aria-label="Entity comparison radar chart across sentiment, review volume, and confidence metrics">
        <PolarGrid />
        <PolarAngleAxis dataKey="metric" tick={{ fontSize: 12 }} />
        <PolarRadiusAxis angle={30} domain={[0, "auto"]} tick={{ fontSize: 10 }} />
        {entities.map((e, i) => (
          <Radar
            key={e.entity_id}
            name={e.entity_name}
            dataKey={e.entity_name}
            stroke={COLORS[i % COLORS.length]}
            fill={COLORS[i % COLORS.length]}
            fillOpacity={0.15}
          />
        ))}
        <Tooltip />
        <Legend />
      </RadarChart>
    </ResponsiveContainer>
    </div>
  )
}
