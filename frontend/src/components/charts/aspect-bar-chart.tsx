"use client"

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import {
  buildAspectSentimentRows,
  type AspectSentimentRow,
  type AspectSortKey,
} from "@/lib/aspect-sentiment"
import { ASPECT_LABELS, type AspectBreakdown } from "@/lib/types"

export type { AspectSortKey } from "@/lib/aspect-sentiment"

interface AspectBarChartProps {
  data: AspectBreakdown[]
  loading?: boolean
  sortBy?: AspectSortKey
  trendDeltas?: Record<string, number>
  onAspectClick?: (aspect: string) => void
  activeAspect?: string | null
}

const sentimentColors = {
  positive: "var(--color-sentiment-positive, #2DD4A7)",
  neutral: "var(--color-sentiment-neutral, #E8B339)",
  negative: "var(--color-sentiment-negative, #FF6B5E)",
}

interface ChartAspectSentimentRow extends AspectSentimentRow {
  displayName: string
}

function formatPercent(value: number) {
  return `${Math.round(value)}%`
}

function AspectTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload?: ChartAspectSentimentRow }>
}) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null

  const values = [
    ["Positive", row.positiveCount, row.positiveShare, sentimentColors.positive],
    ["Neutral", row.neutralCount, row.neutralShare, sentimentColors.neutral],
    ["Negative", row.negativeCount, row.negativeShare, sentimentColors.negative],
  ] as const

  return (
    <div className="min-w-52 rounded-lg border border-border bg-popover p-3 text-sm shadow-xl">
      <p className="font-medium text-popover-foreground">{row.displayName}</p>
      <p className="mb-2 text-xs text-muted-foreground">
        {row.total.toLocaleString()} reviews
      </p>
      <div className="space-y-1.5">
        {values.map(([label, count, share, color]) => (
          <div key={label} className="flex items-center justify-between gap-6">
            <span className="flex items-center gap-2 text-muted-foreground">
              <span
                aria-hidden="true"
                className="size-2 rounded-sm"
                style={{ backgroundColor: color }}
              />
              {label}
            </span>
            <span className="font-medium tabular-nums text-popover-foreground">
              {count.toLocaleString()} · {formatPercent(share)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function AspectBarChart({
  data,
  loading,
  sortBy = "volume",
  trendDeltas,
  onAspectClick,
  activeAspect,
}: AspectBarChartProps) {
  if (loading) {
    return (
      <div className="flex h-80 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading aspects...</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-80 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">
          No aspect data available
        </p>
      </div>
    )
  }

  const chartData = buildAspectSentimentRows(data, sortBy, trendDeltas).map(
    (row) => ({
      ...row,
      displayName: ASPECT_LABELS[row.aspect] ?? row.aspect,
    })
  )
  const clickable = Boolean(onAspectClick)
  const opacityFor = (aspect: string) =>
    activeAspect && activeAspect !== aspect ? 0.25 : 1

  const handleClick = (entry: unknown) => {
    if (!onAspectClick) return
    const item = entry as { aspect?: string; payload?: { aspect?: string } }
    const aspect = item.payload?.aspect ?? item.aspect
    if (aspect) onAspectClick(aspect)
  }

  return (
    <div className="min-w-0 w-full">
      <div
        className="mb-2 flex flex-wrap justify-end gap-x-4 gap-y-1 text-xs text-muted-foreground"
        aria-label="Sentiment legend"
      >
        {[
          ["Positive", sentimentColors.positive],
          ["Neutral", sentimentColors.neutral],
          ["Negative", sentimentColors.negative],
        ].map(([label, color]) => (
          <span key={label} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2.5 rounded-sm"
              style={{ backgroundColor: color }}
            />
            {label}
          </span>
        ))}
      </div>

      <div className="h-80 min-w-0 w-full overflow-hidden">
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          initialDimension={{ width: 600, height: 320 }}
        >
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 4, right: 58, bottom: 4, left: 4 }}
            role="img"
            aria-label="Aspect sentiment mix. Each horizontal bar shows the percentage of positive, neutral, and negative reviews for one aspect."
          >
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis
              type="category"
              dataKey="displayName"
              width={156}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ fill: "var(--color-muted)", opacity: 0.18 }}
              content={<AspectTooltip />}
            />
            <Bar
              dataKey="positiveShare"
              name="Positive"
              stackId="sentiment"
              fill={sentimentColors.positive}
              maxBarSize={30}
              radius={[5, 0, 0, 5]}
              cursor={clickable ? "pointer" : undefined}
              onClick={handleClick}
            >
              {chartData.map((row) => (
                <Cell key={row.aspect} fillOpacity={opacityFor(row.aspect)} />
              ))}
              <LabelList
                dataKey="positiveShare"
                position="center"
                fill="var(--color-sentiment-on-color)"
                fontSize={10}
                fontWeight={600}
                formatter={(value) =>
                  typeof value === "number" && value >= 12
                    ? formatPercent(value)
                    : ""
                }
              />
            </Bar>
            <Bar
              dataKey="neutralShare"
              name="Neutral"
              stackId="sentiment"
              fill={sentimentColors.neutral}
              maxBarSize={30}
              cursor={clickable ? "pointer" : undefined}
              onClick={handleClick}
            >
              {chartData.map((row) => (
                <Cell key={row.aspect} fillOpacity={opacityFor(row.aspect)} />
              ))}
              <LabelList
                dataKey="neutralShare"
                position="center"
                fill="var(--color-sentiment-on-color)"
                fontSize={10}
                fontWeight={600}
                formatter={(value) =>
                  typeof value === "number" && value >= 12
                    ? formatPercent(value)
                    : ""
                }
              />
            </Bar>
            <Bar
              dataKey="negativeShare"
              name="Negative"
              stackId="sentiment"
              fill={sentimentColors.negative}
              maxBarSize={30}
              radius={[0, 5, 5, 0]}
              cursor={clickable ? "pointer" : undefined}
              onClick={handleClick}
            >
              {chartData.map((row) => (
                <Cell key={row.aspect} fillOpacity={opacityFor(row.aspect)} />
              ))}
              <LabelList
                dataKey="negativeShare"
                position="center"
                fill="var(--color-sentiment-on-color)"
                fontSize={10}
                fontWeight={600}
                formatter={(value) =>
                  typeof value === "number" && value >= 12
                    ? formatPercent(value)
                    : ""
                }
              />
              <LabelList
                dataKey="total"
                position="right"
                fill="var(--color-muted-foreground)"
                fontSize={11}
                formatter={(value) =>
                  typeof value === "number"
                    ? `${value.toLocaleString()} reviews`
                    : value
                }
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
