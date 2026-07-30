"use client"

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import type { AspectBreakdown } from "@/lib/types"
import { ASPECT_LABELS } from "@/lib/types"

interface AspectBarChartProps {
  data: AspectBreakdown[]
  loading?: boolean
}

export function AspectBarChart({ data, loading }: AspectBarChartProps) {
  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading aspect data...</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">No aspect data available</p>
      </div>
    )
  }

  const grouped = data.reduce((acc, item) => {
    const aspect = item.aspect
    if (!acc[aspect]) {
      acc[aspect] = { aspect, Positive: 0, Neutral: 0, Negative: 0 }
    }
    const key = item.sentiment.charAt(0).toUpperCase() + item.sentiment.slice(1).toLowerCase()
    if (key in acc[aspect]) {
      acc[aspect][key as "Positive" | "Neutral" | "Negative"] = item.count
    }
    return acc
  }, {} as Record<string, { aspect: string; Positive: number; Neutral: number; Negative: number }>)

  const chartData = Object.values(grouped).map((item) => ({
    ...item,
    displayName: ASPECT_LABELS[item.aspect] ?? item.aspect,
  }))

  return (
    <div className="h-80 min-w-0 w-full overflow-hidden">
    <ResponsiveContainer
      width="100%"
      height="100%"
      minWidth={0}
      initialDimension={{ width: 600, height: 320 }}
    >
      <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }} role="img" aria-label="Aspect sentiment stacked bar chart showing positive, neutral, and negative counts per ABSA aspect">
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="displayName"
          tick={{ fontSize: 11 }}
          interval={0}
          angle={-20}
          textAnchor="end"
          height={60}
        />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Legend />
        <Bar dataKey="Positive" fill="var(--color-green, #22c55e)" stackId="sentiment" />
        <Bar dataKey="Neutral" fill="var(--color-yellow, #eab308)" stackId="sentiment" />
        <Bar dataKey="Negative" fill="var(--color-red, #ef4444)" stackId="sentiment" />
      </BarChart>
    </ResponsiveContainer>
    </div>
  )
}
