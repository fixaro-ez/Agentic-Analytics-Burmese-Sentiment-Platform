"use client"

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import type { SentimentTrendPoint } from "@/lib/types"

interface SentimentTrendChartProps {
  data: SentimentTrendPoint[]
  loading?: boolean
}

/**
 * Recharts AreaChart showing positive / neutral / negative counts over time.
 *
 * Usage:
 *   <SentimentTrendChart data={trends} loading={loading} />
 *
 * Members C and D: follow this pattern for your own chart components.
 */
export function SentimentTrendChart({ data, loading }: SentimentTrendChartProps) {
  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading trend data...</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">No trend data available</p>
      </div>
    )
  }

  return (
    <div className="h-64 min-w-0 w-full overflow-hidden">
    <ResponsiveContainer
      width="100%"
      height="100%"
      minWidth={0}
      initialDimension={{ width: 600, height: 256 }}
    >
      <AreaChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }} role="img" aria-label="Daily positive, neutral, and negative sentiment counts">
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12 }}
          tickFormatter={(v: string) => v.slice(5)} // "2026-07-15" → "07-15"
        />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Legend />
        <Area
          type="monotone"
          dataKey="positive_count"
          name="Positive"
          stroke="#22c55e"
          fill="#22c55e"
          fillOpacity={0.2}
        />
        <Area
          type="monotone"
          dataKey="neutral_count"
          name="Neutral"
          stroke="#eab308"
          fill="#eab308"
          fillOpacity={0.2}
        />
        <Area
          type="monotone"
          dataKey="negative_count"
          name="Negative"
          stroke="#ef4444"
          fill="#ef4444"
          fillOpacity={0.2}
        />
      </AreaChart>
    </ResponsiveContainer>
    </div>
  )
}
