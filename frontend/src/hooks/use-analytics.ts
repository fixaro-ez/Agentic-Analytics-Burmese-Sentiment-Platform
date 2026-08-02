"use client"

import { useMemo } from "react"
import { useApi } from "./use-api"
import type {
  SentimentOverview,
  EntitySentimentOverview,
  AspectBreakdown,
  SentimentTrendPoint,
  FacebookEngagement,
  EntityDetail,
  EntityReviewPage,
  KpiResponse,
  ReactionMix,
  EngagementTrendPoint,
  DriverItem,
  FlaggedReview,
  BenchmarkResponse,
  Brand,
  EtlRunHistory,
  EtlHealthResponse,
} from "@/lib/types"

/** Build a query string from the global entity/date-range filters. */
function filterParams(entityId?: number | null, days?: number | null): string {
  const params = new URLSearchParams()
  if (entityId != null) params.set("entity_id", String(entityId))
  if (days != null) params.set("days", String(days))
  const qs = params.toString()
  return qs ? `?${qs}` : ""
}

// ---------- Dashboard hooks ----------

/** GET /api/analytics/overview — total reviews, positive/negative ratios */
export function useSentimentOverview(entityId?: number | null, days?: number | null) {
  const path = useMemo(
    () => `/api/analytics/overview${filterParams(entityId, days)}`,
    [entityId, days]
  )
  return useApi<SentimentOverview>(path)
}

/** GET /api/analytics/entities — per-entity sentiment breakdown */
export function useEntitySentiments() {
  return useApi<{ entities: EntitySentimentOverview[]; total: number }>(
    "/api/analytics/entities"
  )
}

/** GET /api/analytics/aspects — aspect × sentiment counts */
export function useAspectBreakdown(
  entityId?: number | null,
  days?: number | null,
  options?: { skip?: boolean }
) {
  const path = useMemo(
    () => `/api/analytics/aspects${filterParams(entityId, days)}`,
    [entityId, days]
  )
  return useApi<{ aspects: AspectBreakdown[] }>(path, { skip: options?.skip })
}

/** GET /api/analytics/trends — daily sentiment trend points */
export function useSentimentTrends() {
  return useApi<{ trends: SentimentTrendPoint[] }>("/api/analytics/trends")
}

/** GET /api/analytics/engagement — Facebook engagement per entity */
export function useFacebookEngagement(entityId?: number | null, days?: number | null) {
  const path = useMemo(
    () => `/api/analytics/engagement${filterParams(entityId, days)}`,
    [entityId, days]
  )
  return useApi<{ engagement: FacebookEngagement[] }>(path)
}

/** GET /api/analytics/entities/{entityId} — entity summary and aspects */
export function useEntityDetail(entityId: number) {
  return useApi<EntityDetail>(`/api/analytics/entities/${entityId}`, {
    skip: !entityId,
  })
}

/** GET /api/analytics/entities/{entityId}/reviews — distinct paginated reviews */
export function useEntityReviews(
  entityId: number,
  days: number,
  aspect?: string | null,
  cursor?: string | null,
  focusFeedbackId?: string | null
) {
  const path = useMemo(() => {
    const params = new URLSearchParams()
    params.set("days", String(days))
    params.set("limit", "10")
    if (aspect) params.set("aspect", aspect)
    if (cursor) params.set("cursor", cursor)
    if (focusFeedbackId) params.set("focus_feedback_id", focusFeedbackId)
    return `/api/analytics/entities/${entityId}/reviews?${params}`
  }, [entityId, days, aspect, cursor, focusFeedbackId])
  return useApi<EntityReviewPage>(path, { skip: !entityId })
}

/** GET /api/analytics/trends — daily sentiment trend points with optional filters */
export function useSentimentTrendsFiltered(entityId?: number, days: number = 30) {
  const path = useMemo(() => {
    const params = new URLSearchParams()
    if (entityId) params.set("entity_id", String(entityId))
    params.set("days", String(days))
    return `/api/analytics/trends?${params}`
  }, [entityId, days])
  return useApi<{ trends: SentimentTrendPoint[] }>(path)
}

// ---------- Dashboard v3 hooks ----------

/** GET /api/analytics/kpis — KPI strip: volume trend, sentiment health, Hangry Index */
export function useKpis(entityId?: number | null, days: number = 30) {
  const path = useMemo(
    () => `/api/analytics/kpis${filterParams(entityId, days)}`,
    [entityId, days]
  )
  return useApi<KpiResponse>(path)
}

/** GET /api/analytics/engagement/reactions — Like/Love/Haha reaction mix + ratios */
export function useReactionMix(entityId?: number | null, days?: number | null) {
  const path = useMemo(
    () => `/api/analytics/engagement/reactions${filterParams(entityId, days)}`,
    [entityId, days]
  )
  return useApi<ReactionMix>(path)
}

/** GET /api/analytics/engagement/trends — daily engagement + reaction ratios */
export function useEngagementTrends(entityId?: number | null, days: number = 30) {
  const path = useMemo(
    () => `/api/analytics/engagement/trends${filterParams(entityId, days)}`,
    [entityId, days]
  )
  return useApi<{ trends: EngagementTrendPoint[] }>(path)
}

/** GET /api/analytics/drivers — neg-weighted aspect driver chips */
export function useTopDrivers(
  entityId?: number | null,
  days?: number | null,
  limit: number = 8
) {
  const path = useMemo(() => {
    const qs = filterParams(entityId, days)
    const sep = qs ? "&" : "?"
    return `/api/analytics/drivers${qs}${sep}limit=${limit}`
  }, [entityId, days, limit])
  return useApi<{ drivers: DriverItem[] }>(path)
}

/** GET /api/analytics/reviews/flagged — recently flagged (negative) reviews */
export function useFlaggedReviews(
  entityId?: number | null,
  days?: number | null,
  aspect?: string | null,
  limit: number = 5
) {
  const path = useMemo(() => {
    const params = new URLSearchParams()
    if (entityId != null) params.set("entity_id", String(entityId))
    if (days != null) params.set("days", String(days))
    if (aspect) params.set("aspect", aspect)
    params.set("limit", String(limit))
    return `/api/analytics/reviews/flagged?${params}`
  }, [entityId, days, aspect, limit])
  return useApi<{ reviews: FlaggedReview[] }>(path)
}

function appendIds(
  params: URLSearchParams,
  key: string,
  entityIds: number[]
) {
  entityIds.forEach((id) => params.append(key, String(id)))
}

export function useBrands() {
  return useApi<{ brands: Brand[]; total: number }>("/api/brands")
}

/** GET /api/analytics/benchmark — exact two-brand comparison. */
export function useCompetitorBenchmark(
  brandAId: number | null,
  brandBId: number | null,
  brandABranchIds: number[],
  brandBBranchIds: number[],
  days: number,
  options?: { skip?: boolean }
) {
  const params = new URLSearchParams()
  if (brandAId != null) params.set("brand_a_id", String(brandAId))
  if (brandBId != null) params.set("brand_b_id", String(brandBId))
  appendIds(params, "brand_a_branch_ids", brandABranchIds)
  appendIds(params, "brand_b_branch_ids", brandBBranchIds)
  params.set("days", String(days))
  const path = `/api/analytics/benchmark?${params}`
  return useApi<BenchmarkResponse>(path, { skip: options?.skip })
}

/** GET /api/etl/history — latest pipeline runs (topbar sync badge) */
export function useEtlHistory(limit: number = 1, refetchInterval?: number) {
  return useApi<EtlRunHistory[]>(`/api/etl/history?limit=${limit}`, {
    refetchInterval,
  })
}

/** Fault-tolerant scraper → warehouse health snapshot, refreshed every minute. */
export function useEtlHealth(
  refetchInterval: number = 60_000,
  options?: { skip?: boolean }
) {
  return useApi<EtlHealthResponse>("/api/etl/health", {
    refetchInterval,
    skip: options?.skip,
  })
}
