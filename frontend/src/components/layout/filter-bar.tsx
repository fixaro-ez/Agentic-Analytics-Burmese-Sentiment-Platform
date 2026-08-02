"use client"

import { CalendarDays, FilterX, X } from "lucide-react"
import { usePathname } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useFilterStore,
  hasActiveFilters,
  DATE_RANGE_PRESETS,
  DEFAULT_DAYS,
} from "@/lib/stores/filters"
import { useEntitySentiments } from "@/hooks/use-analytics"
import { myanmarLangProps } from "@/lib/myanmar"
import { ASPECT_LABELS } from "@/lib/types"

const FILTER_BAR_ROUTES = ["/dashboard", "/analytics", "/mining"] as const

function routeUsesGlobalFilters(pathname: string): boolean {
  return FILTER_BAR_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`)
  )
}

/**
 * Shows the shared analysis filters only on routes that consume them.
 */
export function FilterBar() {
  const pathname = usePathname()

  if (!routeUsesGlobalFilters(pathname)) return null

  return <FilterBarControls />
}

function FilterBarControls() {
  const entityId = useFilterStore((s) => s.entityId)
  const days = useFilterStore((s) => s.days)
  const aspect = useFilterStore((s) => s.aspect)
  const setEntity = useFilterStore((s) => s.setEntity)
  const setDays = useFilterStore((s) => s.setDays)
  const setAspect = useFilterStore((s) => s.setAspect)
  const clearFilters = useFilterStore((s) => s.clearFilters)

  const { data: entitiesData } = useEntitySentiments()
  const entities = entitiesData?.entities ?? []
  const nameFor = (id: number) =>
    entities.find((e) => e.entity_id === id)?.entity_name ?? `#${id}`

  const active = hasActiveFilters({ entityId, days, aspect })
  const dayPresets: readonly number[] = DATE_RANGE_PRESETS
  const dayOptions = dayPresets.includes(days)
    ? dayPresets
    : [...dayPresets, days].sort((a, b) => a - b)

  return (
    <div className="sticky top-14 z-20 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex flex-wrap items-center gap-2 px-4 py-2 sm:px-6">
        <Select
          value={entityId != null ? String(entityId) : "all"}
          onValueChange={(v) => setEntity(v === "all" ? null : Number(v))}
        >
          <SelectTrigger
            className="h-11 w-44"
            aria-label="Select entity"
          >
            <SelectValue placeholder="All entities" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All entities</SelectItem>
            {entities.map((e) => (
              <SelectItem
                key={e.entity_id}
                value={String(e.entity_id)}
                {...myanmarLangProps(e.entity_name)}
              >
                {e.entity_name}
              </SelectItem>
            ))}
            {entityId != null &&
              !entities.some((e) => e.entity_id === entityId) && (
                <SelectItem value={String(entityId)}>#{entityId}</SelectItem>
              )}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1.5">
          <CalendarDays
            className="h-4 w-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Select
            value={String(days)}
            onValueChange={(v) => setDays(Number(v))}
          >
            <SelectTrigger className="h-11 w-32" aria-label="Select date range">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {dayOptions.map((d) => (
                <SelectItem key={d} value={String(d)}>
                  Last {d}d
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {active && (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto min-h-11 text-muted-foreground"
            onClick={clearFilters}
          >
            <FilterX className="h-4 w-4" aria-hidden="true" />
            Clear filters
          </Button>
        )}
      </div>

      {active && (
        <div
          className="flex flex-wrap items-center gap-1.5 border-t px-4 py-1.5 sm:px-6"
          aria-label="Active filters"
        >
          <span className="text-xs text-muted-foreground">Filters:</span>
          {entityId != null && (
            <Badge variant="secondary" className="gap-1.5 pr-1">
              <span
                aria-hidden="true"
                className="inline-block h-2 w-2 shrink-0 rounded-full bg-entity-self"
              />
              Entity:{" "}
              <span {...myanmarLangProps(nameFor(entityId))}>
                {nameFor(entityId)}
              </span>
              <button
                type="button"
                className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm hover:bg-accent"
                onClick={() => setEntity(null)}
                aria-label={`Remove entity filter ${nameFor(entityId)}`}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </Badge>
          )}
          {days !== DEFAULT_DAYS && (
            <Badge variant="secondary" className="gap-1.5 pr-1">
              Last {days}d
              <button
                type="button"
                className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm hover:bg-accent"
                onClick={() => setDays(DEFAULT_DAYS)}
                aria-label="Reset date range"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </Badge>
          )}
          {aspect && (
            <Badge variant="secondary" className="gap-1.5 pr-1">
              Aspect: {ASPECT_LABELS[aspect] ?? aspect}
              <button
                type="button"
                className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm hover:bg-accent"
                onClick={() => setAspect(null)}
                aria-label={`Remove aspect filter ${ASPECT_LABELS[aspect] ?? aspect}`}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </Badge>
          )}
        </div>
      )}
    </div>
  )
}
