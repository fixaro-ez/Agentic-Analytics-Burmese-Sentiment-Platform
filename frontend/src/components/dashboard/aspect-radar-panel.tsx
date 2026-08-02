"use client"

import { useState } from "react"

import { EntityComparisonPicker } from "@/components/analytics/entity-comparison-picker"
import { EntityRadar, type AspectRadarSeries } from "@/components/charts/entity-radar"
import { useAspectBreakdown, useEntitySentiments } from "@/hooks/use-analytics"
import { useFilterStore } from "@/lib/stores/filters"

/**
 * Filter-aware wrapper around the 6-axis aspect radar. The primary series
 * follows the global entity filter; comparison entities are local to this
 * chart so unrelated dashboard panels keep a single, predictable scope.
 */
export function AspectRadarPanel() {
  const entityId = useFilterStore((s) => s.entityId)
  const days = useFilterStore((s) => s.days)
  const [comparison, setComparison] = useState<{
    primaryEntityId: number | null
    ids: number[]
  }>({ primaryEntityId: null, ids: [] })
  const compareIds =
    comparison.primaryEntityId === entityId ? comparison.ids : []

  const primary = useAspectBreakdown(entityId, days)
  const compare1 = useAspectBreakdown(compareIds[0] ?? null, days, {
    skip: compareIds[0] == null,
  })
  const compare2 = useAspectBreakdown(compareIds[1] ?? null, days, {
    skip: compareIds[1] == null,
  })

  const { data: entitiesData } = useEntitySentiments()
  const nameFor = (id: number | null) =>
    id == null
      ? "All entities"
      : (entitiesData?.entities.find((e) => e.entity_id === id)?.entity_name ??
        `#${id}`)

  const series: AspectRadarSeries[] = [
    { name: nameFor(entityId), aspects: primary.data?.aspects ?? [] },
    ...([compareIds[0], compareIds[1]] as const)
      .filter((id): id is number => id != null)
      .map((id, i) => ({
        name: nameFor(id),
        aspects: (i === 0 ? compare1 : compare2).data?.aspects ?? [],
      })),
  ]

  const loading =
    primary.loading ||
    (compareIds[0] != null && compare1.loading) ||
    (compareIds[1] != null && compare2.loading)

  return (
    <div className="space-y-3">
      <EntityComparisonPicker
        primaryEntityId={entityId}
        selectedIds={compareIds}
        onChange={(ids) => setComparison({ primaryEntityId: entityId, ids })}
        label="Compare radar with"
      />
      <EntityRadar series={series} loading={loading} />
    </div>
  )
}
