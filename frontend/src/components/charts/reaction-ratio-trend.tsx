"use client"

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { EngagementTrendPoint } from "@/lib/types"

interface ReactionRatioTrendProps {
  data: EngagementTrendPoint[]
  loading?: boolean
}

export function ReactionRatioTrend({
  data,
  loading,
}: ReactionRatioTrendProps) {
  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          Loading reaction trends...
        </p>
      </div>
    )
  }

  if (!data.length) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">
          No reaction trend data available
        </p>
      </div>
    )
  }

  const chartData = data.map((point) => ({
    ...point,
    positivity_pct:
      point.positivity_ratio == null ? null : point.positivity_ratio * 100,
    negativity_pct:
      point.negativity_ratio == null ? null : point.negativity_ratio * 100,
    haha_pct: point.haha_ratio == null ? null : point.haha_ratio * 100,
  }))

  return (
    <div className="h-64 min-w-0 w-full overflow-hidden">
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={0}
        initialDimension={{ width: 560, height: 256 }}
      >
        <LineChart
          data={chartData}
          margin={{ top: 8, right: 16, bottom: 4, left: 0 }}
          role="img"
          aria-label="Facebook positivity, negativity, and haha reaction ratios over time"
        >
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11 }}
            tickFormatter={(value: string) => value.slice(5)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 11 }}
            tickFormatter={(value: number) => `${value}%`}
          />
          <Tooltip
            formatter={(value, name) => {
              const raw = Array.isArray(value) ? value[0] : value
              return [
                raw == null ? "N/A" : `${Number(raw).toFixed(1)}%`,
                String(name ?? "Ratio"),
              ]
            }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="positivity_pct"
            name="Positivity"
            stroke="var(--color-sentiment-positive, #2DD4A7)"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="negativity_pct"
            name="Negativity"
            stroke="var(--color-sentiment-negative, #FF6B5E)"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="haha_pct"
            name="Haha"
            stroke="var(--color-alert-sarcasm, #C77DFF)"
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
