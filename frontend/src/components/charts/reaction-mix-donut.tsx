"use client"

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts"
import type { ReactionMix } from "@/lib/types"

interface ReactionMixDonutProps {
  data: ReactionMix
  loading?: boolean
}

// Reaction identity colors — distinct from sentiment tokens so the donut is
// never misread as a sentiment chart (angry/sad use sentiment hues since they
// genuinely are negative signals).
type ReactionKey =
  | "like"
  | "love"
  | "care"
  | "haha"
  | "wow"
  | "sad"
  | "angry"

const REACTION_COLORS: Record<ReactionKey, string> = {
  like: "var(--color-entity-self, #5B8DEF)",
  love: "var(--color-entity-compare-2, #F472B6)",
  care: "var(--color-entity-compare-1, #38BDF8)",
  haha: "var(--color-alert-sarcasm, #c77dff)",
  wow: "var(--color-muted-foreground, #8B98A5)",
  sad: "var(--color-badge-incomplete, #4B5563)",
  angry: "var(--color-sentiment-negative, #FF6B5E)",
}

const REACTION_LABELS: Record<ReactionKey, string> = {
  like: "Like",
  love: "Love",
  care: "Care",
  haha: "Haha",
  wow: "Wow",
  sad: "Sad",
  angry: "Angry",
}

/**
 * Like/Love/Haha reaction-mix donut (v3 spec §1.1 social engagement panel).
 * Posts with an incomplete reaction breakdown are excluded upstream and
 * surfaced via the panel's "Data Incomplete" badge — never coerced to zero.
 */
export function ReactionMixDonut({ data, loading }: ReactionMixDonutProps) {
  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading reaction data...</p>
      </div>
    )
  }

  const chartData = (Object.keys(REACTION_LABELS) as ReactionKey[])
    .map((key) => ({ name: REACTION_LABELS[key], key, value: data[key] ?? 0 }))
    .filter((d) => d.value > 0)

  const total = chartData.reduce((sum, d) => sum + d.value, 0)

  if (total === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">
          No reaction breakdown available
          {data.incomplete_posts > 0
            ? ` — ${data.incomplete_posts} of ${data.total_posts} posts missing data`
            : ""}
        </p>
      </div>
    )
  }

  return (
    <div className="h-64 min-w-0 w-full overflow-hidden">
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={0}
        initialDimension={{ width: 320, height: 256 }}
      >
        <PieChart role="img" aria-label="Facebook reaction mix donut chart">
          <Pie
            data={chartData}
            dataKey="value"
            nameKey="name"
            innerRadius="55%"
            outerRadius="80%"
            paddingAngle={2}
          >
            {chartData.map((d) => (
              <Cell key={d.key} fill={REACTION_COLORS[d.key]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name) => {
              const numeric = Number(
                Array.isArray(value) ? value[0] : (value ?? 0)
              )
              return [
                `${numeric.toLocaleString()} (${((numeric / total) * 100).toFixed(1)}%)`,
                String(name ?? "Reaction"),
              ]
            }}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
