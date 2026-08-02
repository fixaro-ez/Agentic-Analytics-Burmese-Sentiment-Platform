"use client"

import type { ReactNode } from "react"
import { TrendingDown, TrendingUp } from "lucide-react"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { DailyVolume } from "@/lib/types"

interface KpiCardProps {
  label: string
  value: ReactNode
  loading?: boolean
  /** Signed delta vs the previous period (percentage points or %). */
  delta?: number | null
  /** Format override for the delta, e.g. (d) => `${d} pts`. Defaults to signed %. */
  formatDelta?: (delta: number) => string
  /** When true, a negative delta is the "good" direction (e.g. Hangry Index, backlog). */
  invertDelta?: boolean
  caption?: string
  /** Optional mini trend rendered under the value. */
  sparkline?: DailyVolume[]
  /** Extra classes on the value (e.g. sentiment/accent token text colors). */
  valueClassName?: string
  /** Deep-link handler — cards are entry points, not endpoints (v3 spec §4). */
  onClick?: () => void
  clickLabel?: string
}

/** Tiny inline SVG sparkline (no chart library needed at this size). */
function Sparkline({ data }: { data: DailyVolume[] }) {
  if (data.length < 2) return null
  const width = 96
  const height = 28
  const max = Math.max(...data.map((d) => d.count), 1)
  const step = width / (data.length - 1)
  const points = data
    .map((d, i) => `${(i * step).toFixed(1)},${(height - (d.count / max) * height).toFixed(1)}`)
    .join(" ")
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-7 w-24"
      aria-hidden="true"
      focusable="false"
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--color-accent-primary, #5B8DEF)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

/**
 * Clickable KPI card (v3 spec §1.1): KPI cards are entry points — clicking
 * deep-links to the relevant detail panel (scroll + filter), never a dead end.
 */
export function KpiCard({
  label,
  value,
  loading,
  delta,
  formatDelta,
  invertDelta,
  caption,
  sparkline,
  valueClassName,
  onClick,
  clickLabel,
}: KpiCardProps) {
  const showDelta = delta != null && !loading
  const deltaGood = showDelta && (invertDelta ? delta <= 0 : delta >= 0)
  const DeltaIcon = showDelta && delta < 0 ? TrendingDown : TrendingUp

  return (
    <Card
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={onClick ? (clickLabel ?? `${label}: open details`) : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                onClick()
              }
            }
          : undefined
      }
      className={cn(
        "min-w-56 flex-1",
        onClick &&
          "cursor-pointer transition-colors hover:border-accent-primary/60 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
    >
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        {loading ? (
          <Skeleton className="h-8 w-20" />
        ) : (
          <CardTitle className={cn("text-2xl", valueClassName)}>{value}</CardTitle>
        )}
        {showDelta && (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-xs font-medium",
              deltaGood
                ? "text-sentiment-positive-foreground"
                : "text-sentiment-negative-foreground"
            )}
          >
            <DeltaIcon className="h-3.5 w-3.5" aria-hidden="true" />
            {formatDelta ? formatDelta(delta) : `${delta >= 0 ? "+" : ""}${delta}%`}
            <span className="font-normal text-muted-foreground">vs prev period</span>
          </span>
        )}
        {caption && !loading && (
          <span className="text-xs text-muted-foreground">{caption}</span>
        )}
        {sparkline && sparkline.length > 1 && !loading && (
          <Sparkline data={sparkline} />
        )}
      </CardHeader>
    </Card>
  )
}
