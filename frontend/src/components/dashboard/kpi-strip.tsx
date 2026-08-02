"use client"

import { KpiCard } from "@/components/dashboard/kpi-card"
import { useKpis } from "@/hooks/use-analytics"
import { useFilterStore } from "@/lib/stores/filters"

function sentimentHealthPresentation(score: number | null | undefined) {
  if (score == null) return { className: undefined, caption: undefined }
  if (score < 50) {
    return {
      className: "text-sentiment-negative-foreground",
      caption: "Low sentiment health",
    }
  }
  if (score < 70) {
    return {
      className: "text-sentiment-neutral-foreground",
      caption: "Moderate sentiment health",
    }
  }
  return {
    className: "text-sentiment-positive-foreground",
    caption: "Healthy sentiment",
  }
}

/** Smooth-scroll to a dashboard panel by element id. */
export function scrollToPanel(id: string) {
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: "smooth", block: "start" })
}

/**
 * KPI strip (v3 spec §1.1): Review Volume (sparkline + trend), Sentiment
 * Health (0–100), and Hangry Index (speed/quality negativity). Cards
 * deep-link into the filtered detail panels. Horizontal scroll on narrow
 * viewports per the spec.
 */
export function KpiStrip() {
  const entityId = useFilterStore((s) => s.entityId)
  const days = useFilterStore((s) => s.days)
  const setAspect = useFilterStore((s) => s.setAspect)

  const { data: kpis, loading } = useKpis(entityId, days)
  const sentimentHealth = sentimentHealthPresentation(kpis?.sentiment_health)
  return (
    <div
      className="flex gap-4 overflow-x-auto pb-1 lg:grid lg:grid-cols-3 lg:overflow-visible lg:pb-0"
      aria-label="Key performance indicators"
    >
      <KpiCard
        label="Review Volume"
        value={kpis?.total_reviews?.toLocaleString() ?? "—"}
        loading={loading}
        delta={kpis?.volume_delta_pct}
        sparkline={kpis?.daily_volumes}
        onClick={() => scrollToPanel("panel-trends")}
        clickLabel="Review Volume: jump to sentiment trend"
      />
      <KpiCard
        label="Sentiment Health"
        value={
          kpis?.sentiment_health != null
            ? `${kpis.sentiment_health.toFixed(0)}/100`
            : "—"
        }
        loading={loading}
        delta={kpis?.sentiment_health_delta}
        formatDelta={(d) => `${d >= 0 ? "+" : ""}${d} pts`}
        valueClassName={sentimentHealth.className}
        caption={sentimentHealth.caption}
        onClick={() => scrollToPanel("panel-aspects")}
        clickLabel="Sentiment Health: jump to aspect breakdown"
      />
      <KpiCard
        label="Hangry Index"
        value={kpis?.hangry_index != null ? kpis.hangry_index.toFixed(2) : "—"}
        loading={loading}
        delta={kpis?.hangry_delta}
        formatDelta={(d) => `${d >= 0 ? "+" : ""}${d.toFixed(2)}`}
        invertDelta
        caption="speed & quality negativity"
        valueClassName="text-accent-hangry"
        onClick={() => {
          setAspect("fulfillment_and_speed")
          scrollToPanel("panel-aspects")
        }}
        clickLabel="Hangry Index: filter by Fulfillment & Speed aspect"
      />
    </div>
  )
}
