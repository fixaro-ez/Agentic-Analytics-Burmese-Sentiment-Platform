"use client"

import { AlertTriangle } from "lucide-react"
import { DataError } from "@/components/data-error"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useFlaggedReviews,
  useTopDrivers,
} from "@/hooks/use-analytics"
import { myanmarLangProps } from "@/lib/myanmar"
import { useFilterStore } from "@/lib/stores/filters"
import { ASPECT_LABELS } from "@/lib/types"
import { cn } from "@/lib/utils"

export function TopDriversPanel() {
  const entityId = useFilterStore((state) => state.entityId)
  const days = useFilterStore((state) => state.days)
  const aspect = useFilterStore((state) => state.aspect)
  const setAspect = useFilterStore((state) => state.setAspect)

  const drivers = useTopDrivers(entityId, days, 6)
  const flagged = useFlaggedReviews(entityId, days, aspect, 4)

  if (drivers.error) {
    return <DataError message={drivers.error} onRetry={drivers.refetch} />
  }
  if (flagged.error) {
    return <DataError message={flagged.error} onRetry={flagged.refetch} />
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="mb-2 text-sm font-medium">Negative sentiment drivers</p>
        {drivers.loading ? (
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-8 w-28" />
            ))}
          </div>
        ) : drivers.data?.drivers.length ? (
          <div className="flex flex-wrap gap-2">
            {drivers.data.drivers.map((driver) => {
              const active = aspect === driver.aspect
              return (
                <Button
                  key={driver.aspect}
                  variant={active ? "secondary" : "outline"}
                  size="sm"
                  className={cn(
                    "h-auto min-h-9 max-w-full whitespace-normal px-3 py-1.5 text-left",
                    active && "border-sentiment-negative/60"
                  )}
                  aria-pressed={active}
                  onClick={() => setAspect(active ? null : driver.aspect)}
                  title={`${driver.negative_count} negative of ${driver.total_count} results`}
                >
                  {ASPECT_LABELS[driver.aspect] ?? driver.aspect}
                  <span className="text-sentiment-negative-foreground">
                    {(driver.negative_share * 100).toFixed(0)}%
                  </span>
                </Button>
              )
            })}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No negative drivers in this filter window.
          </p>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2">
          <AlertTriangle
            className="h-4 w-4 text-alert-critical"
            aria-hidden="true"
          />
          <p className="text-sm font-medium">Recently flagged reviews</p>
        </div>
        {flagged.loading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full" />
            ))}
          </div>
        ) : flagged.data?.reviews.length ? (
          <ul className="space-y-2">
            {flagged.data.reviews.map((review, index) => (
              <li
                key={`${review.created_at ?? "unknown"}-${index}`}
                className="rounded-lg border bg-muted/20 p-3"
              >
                <p
                  className="line-clamp-2 text-sm leading-relaxed"
                  {...myanmarLangProps(review.review_text)}
                >
                  {review.review_text || "Review text unavailable"}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  {review.entity_name && (
                    <span {...myanmarLangProps(review.entity_name)}>
                      {review.entity_name}
                    </span>
                  )}
                  {review.aspect_category && (
                    <Badge variant="outline" className="text-[11px]">
                      {ASPECT_LABELS[review.aspect_category] ??
                        review.aspect_category}
                    </Badge>
                  )}
                  {review.confidence_score != null && (
                    <span>
                      {(review.confidence_score * 100).toFixed(0)}% confidence
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No flagged reviews match the active filters.
          </p>
        )}
      </div>
    </div>
  )
}
