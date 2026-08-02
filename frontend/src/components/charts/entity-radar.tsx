"use client"

import { useMemo, useState } from "react"
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
import { ASPECT_LABELS, type AspectBreakdown } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// Entity-series identity colors (v3 spec §3.6): self / compare-1 / compare-2.
const SERIES_COLORS = [
  "var(--color-entity-self, #5B8DEF)",
  "var(--color-entity-compare-1, #38BDF8)",
  "var(--color-entity-compare-2, #F472B6)",
]

/** One entity's aspect breakdown rendered as a radar series. */
export interface AspectRadarSeries {
  name: string
  aspects: AspectBreakdown[]
}

interface EntityRadarProps {
  /** Primary entity first, then up to 2 compare entities (v3 compare mode). */
  series: AspectRadarSeries[]
  loading?: boolean
}

interface AspectAggregate {
  positive: number
  neutral: number
  negative: number
  total: number
  avgConfidence: number | null
}

function aggregateAspects(rows: AspectBreakdown[]): Map<string, AspectAggregate> {
  const map = new Map<string, AspectAggregate>()
  for (const row of rows) {
    const agg =
      map.get(row.aspect) ??
      ({ positive: 0, neutral: 0, negative: 0, total: 0, avgConfidence: null } as AspectAggregate)
    const sentiment = row.sentiment.toLowerCase()
    if (sentiment === "positive") agg.positive += row.count
    else if (sentiment === "negative") agg.negative += row.count
    else if (sentiment === "neutral") agg.neutral += row.count
    agg.total += row.count
    map.set(row.aspect, agg)
  }
  // Confidence: count-weighted mean across sentiment rows.
  for (const [aspect, agg] of map) {
    const relevant = rows.filter((r) => r.aspect === aspect && r.count > 0)
    const weight = relevant.reduce((sum, r) => sum + r.count, 0)
    agg.avgConfidence = weight
      ? relevant.reduce((sum, r) => sum + r.avg_confidence * r.count, 0) / weight
      : null
  }
  return map
}

const ASPECT_KEYS = Object.keys(ASPECT_LABELS)

/**
 * 6-axis ABSA aspect radar (v3 spec §1.1): one axis per aspect, entity A vs B
 * overlay in compare mode, and a volume-weighted / raw toggle.
 * Raw mode: per-aspect positive share (%). Volume-weighted: positive share
 * scaled by the aspect's share of the entity's review volume, so high-volume
 * aspects dominate the shape. Hover shows n reviews + avg confidence.
 */
export function EntityRadar({ series, loading }: EntityRadarProps) {
  const [weighted, setWeighted] = useState(false)

  const aggregates = useMemo(
    () => series.map((s) => aggregateAspects(s.aspects)),
    [series]
  )

  const chartData = useMemo(() => {
    return ASPECT_KEYS.map((aspectKey) => {
      const point: Record<string, string | number | null> = {
        metric: ASPECT_LABELS[aspectKey] ?? aspectKey,
      }
      series.forEach((s, i) => {
        const agg = aggregates[i].get(aspectKey)
        const positiveShare = agg && agg.total > 0 ? (agg.positive / agg.total) * 100 : 0
        // Volume weight: this aspect's share of the entity's largest aspect.
        const maxTotal = Math.max(
          ...ASPECT_KEYS.map((k) => aggregates[i].get(k)?.total ?? 0),
          1
        )
        const weight = agg ? agg.total / maxTotal : 0
        point[s.name] = Math.round((weighted ? positiveShare * weight : positiveShare) * 10) / 10
        point[`${s.name}__n`] = agg?.total ?? 0
        point[`${s.name}__conf`] =
          agg?.avgConfidence != null ? Math.round(agg.avgConfidence * 100) : null
      })
      return point
    })
  }, [series, aggregates, weighted])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading aspect data...</p>
      </div>
    )
  }

  const hasData = series.some((s) => s.aspects.length > 0)
  if (!series.length || !hasData) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">No aspect data available</p>
      </div>
    )
  }

  return (
    <div className="min-w-0 w-full">
      <div
        className="mb-1 flex justify-end gap-1"
        role="group"
        aria-label="Radar weighting mode"
      >
        <Button
          variant={weighted ? "ghost" : "secondary"}
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => setWeighted(false)}
          aria-pressed={!weighted}
        >
          Raw
        </Button>
        <Button
          variant={weighted ? "secondary" : "ghost"}
          size="sm"
          className={cn("h-7 px-2 text-xs")}
          onClick={() => setWeighted(true)}
          aria-pressed={weighted}
        >
          Volume-weighted
        </Button>
      </div>
      <div className="h-80 min-w-0 w-full overflow-hidden">
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          initialDimension={{ width: 500, height: 320 }}
        >
          <RadarChart data={chartData} outerRadius="70%" role="img" aria-label="Six-axis ABSA aspect radar chart">
            <PolarGrid />
            <PolarAngleAxis dataKey="metric" tick={{ fontSize: 10 }} />
            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9 }} />
            {series.map((s, i) => (
              <Radar
                key={s.name}
                name={s.name}
                dataKey={s.name}
                stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                fillOpacity={0.15}
              />
            ))}
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const axis = payload[0]?.payload as Record<string, string | number | null>
                return (
                  <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
                    <p className="mb-1 font-medium">{axis.metric}</p>
                    {series.map((s, i) => (
                      <p
                        key={s.name}
                        style={{ color: SERIES_COLORS[i % SERIES_COLORS.length] }}
                      >
                        {s.name}: {axis[s.name] ?? 0}%
                        {weighted ? " (weighted)" : ""} · {axis[`${s.name}__n`]} reviews
                        {axis[`${s.name}__conf`] != null
                          ? ` · ${axis[`${s.name}__conf`]}% conf`
                          : ""}
                      </p>
                    ))}
                  </div>
                )
              }}
            />
            <Legend />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
