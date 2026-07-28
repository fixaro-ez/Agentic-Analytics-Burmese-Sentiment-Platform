"use client"

import { useApi } from "./use-api"
import type {
  SentimentOverview,
  EntitySentimentOverview,
  AspectBreakdown,
  SentimentTrendPoint,
  FacebookEngagement,
} from "@/lib/types"

// ---------- Dashboard hooks ----------

/** GET /api/analytics/overview — total reviews, positive/negative ratios */
export function useSentimentOverview() {
  return useApi<SentimentOverview>("/api/analytics/overview")
}

/** GET /api/analytics/entities — per-entity sentiment breakdown */
export function useEntitySentiments() {
  return useApi<{ entities: EntitySentimentOverview[]; total: number }>(
    "/api/analytics/entities"
  )
}

/** GET /api/analytics/aspects — aspect × sentiment counts */
export function useAspectBreakdown() {
  return useApi<{ aspects: AspectBreakdown[] }>("/api/analytics/aspects")
}

/** GET /api/analytics/trends — daily sentiment trend points */
export function useSentimentTrends() {
  return useApi<{ trends: SentimentTrendPoint[] }>("/api/analytics/trends")
}

/** GET /api/analytics/engagement — Facebook engagement per entity */
export function useFacebookEngagement() {
  return useApi<{ engagement: FacebookEngagement[] }>(
    "/api/analytics/engagement"
  )
}
