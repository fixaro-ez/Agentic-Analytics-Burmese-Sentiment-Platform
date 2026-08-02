"use client"

import { useMemo, useState } from "react"
import { AspectBarChart, type AspectSortKey } from "@/components/charts/aspect-bar-chart"
import { DataError } from "@/components/data-error"
import { Button } from "@/components/ui/button"
import { useAspectBreakdown } from "@/hooks/use-analytics"
import { useFilterStore } from "@/lib/stores/filters"
import { cn } from "@/lib/utils"
import type { AspectBreakdown } from "@/lib/types"

const SORT_OPTIONS: { key: AspectSortKey; label: string }[] = [
  { key: "volume", label: "Volume" },
  { key: "negativity", label: "Negativity" },
  { key: "trend", label: "Trend Δ" },
]

/**
 * Aspect breakdown panel (v3 spec §1.1): stacked Positive/Neutral/Negative
 * bars per ABSA aspect, sortable by volume / negativity / trend delta.
 * Clicking a bar sets the global aspect filter (every chart is a filter).
 */
export function AspectBreakdownPanel() {
  const entityId = useFilterStore((s) => s.entityId)
  const days = useFilterStore((s) => s.days)
  const aspect = useFilterStore((s) => s.aspect)
  const setAspect = useFilterStore((s) => s.setAspect)

  const [sortBy, setSortBy] = useState<AspectSortKey>("volume")

  const current = useAspectBreakdown(entityId, days)
  // Double-window fetch lets us approximate the previous period's counts:
  // prev = (2×window) − current. Only needed for the "trend" sort.
  // Clamped to 365 (backend max).
  const doubleWindow = useAspectBreakdown(
    entityId,
    sortBy === "trend" ? Math.min(days * 2, 365) : null,
    { skip: sortBy !== "trend" }
  )

  const trendDeltas = useMemo(() => {
    if (sortBy !== "trend" || !current.data || !doubleWindow.data) return undefined
    const negCount = (rows: AspectBreakdown[]) => {
      const map: Record<string, number> = {}
      for (const row of rows) {
        if (row.sentiment.toLowerCase() === "negative") {
          map[row.aspect] = (map[row.aspect] ?? 0) + row.count
        }
      }
      return map
    }
    const cur = negCount(current.data.aspects)
    const dbl = negCount(doubleWindow.data.aspects)
    const deltas: Record<string, number> = {}
    for (const aspectKey of new Set([...Object.keys(cur), ...Object.keys(dbl)])) {
      const c = cur[aspectKey] ?? 0
      // Previous-window negatives = (double-window total) − (current total).
      deltas[aspectKey] = c - ((dbl[aspectKey] ?? 0) - c)
    }
    return deltas
  }, [sortBy, current.data, doubleWindow.data])

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1" role="group" aria-label="Sort aspects by">
        <span className="mr-1 text-xs text-muted-foreground">Sort:</span>
        {SORT_OPTIONS.map((opt) => (
          <Button
            key={opt.key}
            variant={sortBy === opt.key ? "secondary" : "ghost"}
            size="sm"
            className={cn("h-7 px-2 text-xs")}
            onClick={() => setSortBy(opt.key)}
            aria-pressed={sortBy === opt.key}
          >
            {opt.label}
          </Button>
        ))}
        {aspect && (
          <span className="ml-auto text-xs text-muted-foreground">
            Filtered to this aspect — clear from the filter bar above.
          </span>
        )}
      </div>
      {current.error ? (
        <DataError message={current.error} onRetry={current.refetch} />
      ) : (
        <AspectBarChart
          data={current.data?.aspects ?? []}
          loading={current.loading || (sortBy === "trend" && doubleWindow.loading)}
          sortBy={sortBy}
          trendDeltas={trendDeltas}
          activeAspect={aspect}
          onAspectClick={(a) => setAspect(aspect === a ? null : a)}
        />
      )}
    </div>
  )
}
