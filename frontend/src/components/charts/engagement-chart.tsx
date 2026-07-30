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
import type { FacebookEngagement } from "@/lib/types"

interface EngagementChartProps {
  data: FacebookEngagement[]
  loading?: boolean
}

export function EngagementChart({ data, loading }: EngagementChartProps) {
  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading engagement data...</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">No engagement data available</p>
      </div>
    )
  }

  const chartData = data.map((e) => ({
    name: e.entity_name,
    total_reactions: e.total_reactions ?? 0,
    total_shares: e.total_shares ?? 0,
    total_comments: e.total_comments ?? 0,
  }))

  return (
    <div className="h-80 min-w-0 w-full overflow-hidden">
    <ResponsiveContainer
      width="100%"
      height="100%"
      minWidth={0}
      initialDimension={{ width: 900, height: 320 }}
    >
      <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }} role="img" aria-label="Facebook engagement chart showing reactions, shares, and comments per entity">
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Legend />
        <Bar dataKey="total_reactions" name="Reactions" fill="var(--color-facebook, #1877f2)" maxBarSize={72} />
        <Bar dataKey="total_shares" name="Shares" fill="var(--color-green, #42b72a)" maxBarSize={72} />
        <Bar dataKey="total_comments" name="Comments" fill="var(--color-yellow, #f7b928)" maxBarSize={72} />
      </BarChart>
    </ResponsiveContainer>
    </div>
  )
}
