"use client"

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { aggregateSentimentByWeek } from "@/lib/sentiment-balance"
import type { WeeklySentimentPoint } from "@/lib/sentiment-balance"
import type { SentimentTrendPoint } from "@/lib/types"

interface SentimentTrendChartProps {
  data: SentimentTrendPoint[]
  loading?: boolean
}

const sentimentColors = {
  positive: "var(--color-sentiment-positive, #2DD4A7)",
  neutral: "var(--color-sentiment-neutral, #E8B339)",
  negative: "var(--color-sentiment-negative, #FF6B5E)",
}

function formatShare(count: number, total: number) {
  return total > 0 ? `${Math.round((count / total) * 100)}%` : "0%"
}

function SentimentTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload?: WeeklySentimentPoint }>
}) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null

  const rows = [
    ["Positive", point.positiveCount, sentimentColors.positive],
    ["Neutral", point.neutralCount, sentimentColors.neutral],
    ["Negative", point.negativeCount, sentimentColors.negative],
  ] as const

  return (
    <div className="min-w-48 rounded-lg border border-border bg-popover p-3 text-sm shadow-xl">
      <p className="font-medium text-popover-foreground">{point.weekRange}</p>
      <p className="mb-2 text-xs text-muted-foreground">
        {point.totalReviews.toLocaleString()} reviews
      </p>
      <div className="space-y-1.5">
        {rows.map(([label, count, color]) => (
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
              {count.toLocaleString()} · {formatShare(count, point.totalReviews)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function SentimentTrendChart({
  data,
  loading,
}: SentimentTrendChartProps) {
  if (loading) {
    return (
      <div className="flex h-72 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading sentiment...</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">
          No sentiment data available
        </p>
      </div>
    )
  }

  const weeklyData = aggregateSentimentByWeek(data)

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

      <div className="h-72 min-w-0 w-full overflow-hidden">
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          initialDimension={{ width: 600, height: 288 }}
        >
          <ComposedChart
            data={weeklyData}
            stackOffset="sign"
            margin={{ top: 22, right: 12, bottom: 2, left: 0 }}
            role="img"
            aria-label="Weekly sentiment balance. Positive and neutral reviews appear above zero; negative reviews appear below zero."
          >
            <CartesianGrid
              vertical={false}
              strokeDasharray="3 3"
              className="stroke-muted"
            />
            <XAxis
              dataKey="weekLabel"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) => Math.abs(value).toLocaleString()}
              width={34}
            />
            <Tooltip
              cursor={{ fill: "var(--color-muted)", opacity: 0.2 }}
              content={<SentimentTooltip />}
            />
            <ReferenceLine
              y={0}
              stroke="var(--color-border)"
              strokeWidth={1.5}
            />
            <Bar
              dataKey="neutralCount"
              name="Neutral"
              stackId="sentiment"
              fill={sentimentColors.neutral}
              maxBarSize={64}
            />
            <Bar
              dataKey="positiveCount"
              name="Positive"
              stackId="sentiment"
              fill={sentimentColors.positive}
              maxBarSize={64}
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="negativeValue"
              name="Negative"
              stackId="sentiment"
              fill={sentimentColors.negative}
              maxBarSize={64}
              radius={[0, 0, 4, 4]}
            />
            <Line
              dataKey="aboveTotal"
              stroke="transparent"
              dot={false}
              activeDot={false}
              legendType="none"
              isAnimationActive={false}
            >
              <LabelList
                dataKey="totalReviews"
                position="top"
                fill="var(--color-muted-foreground)"
                fontSize={11}
                formatter={(value) =>
                  typeof value === "number" ? value.toLocaleString() : value
                }
              />
            </Line>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
