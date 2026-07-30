"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { SentimentTrendChart } from "@/components/charts/sentiment-trend-chart"
import { AspectBarChart } from "@/components/charts/aspect-bar-chart"
import { EngagementChart } from "@/components/charts/engagement-chart"
import { EntityRadar } from "@/components/charts/entity-radar"
import { DataError } from "@/components/data-error"
import {
  useSentimentTrendsFiltered,
  useAspectBreakdown,
  useFacebookEngagement,
  useEntitySentiments,
} from "@/hooks/use-analytics"

export default function AnalyticsPage() {
  const [days, setDays] = useState(30)
  const [entityFilter, setEntityFilter] = useState<number | undefined>(undefined)

  const {
    data: entitiesData,
    loading: loadingEntities,
    error: entitiesError,
    refetch: refetchEntities,
  } = useEntitySentiments()
  const {
    data: trendsData,
    loading: loadingTrends,
    error: trendsError,
    refetch: refetchTrends,
  } = useSentimentTrendsFiltered(entityFilter, days)
  const {
    data: aspectsData,
    loading: loadingAspects,
    error: aspectsError,
    refetch: refetchAspects,
  } = useAspectBreakdown()
  const {
    data: engagementData,
    loading: loadingEngagement,
    error: engagementError,
    refetch: refetchEngagement,
  } = useFacebookEngagement()

  const entities = entitiesData?.entities ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground">
          Deep-dive into sentiment trends, aspect analysis, and engagement metrics.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="min-w-0">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Sentiment Over Time</CardTitle>
                <CardDescription>
                  Track positive, neutral, and negative sentiment trends
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              {[7, 30, 90].map((d) => (
                <Button
                  key={d}
                  variant={days === d ? "default" : "outline"}
                  size="sm"
                  onClick={() => setDays(d)}
                >
                  {d}d
                </Button>
              ))}
            </div>
            <div className="space-y-1">
              <label htmlFor="entity-filter" className="text-sm font-medium text-muted-foreground">
                Filter by entity
              </label>
              <select
                id="entity-filter"
                className="w-full rounded-md border px-3 py-1.5 text-sm bg-background"
                value={entityFilter ?? ""}
                onChange={(e) =>
                  setEntityFilter(e.target.value ? Number(e.target.value) : undefined)
                }
              >
                <option value="">All entities</option>
                {entities.map((e) => (
                  <option key={e.entity_id} value={e.entity_id}>
                    {e.entity_name}
                  </option>
                ))}
              </select>
            </div>
            {trendsError ? (
              <DataError message={trendsError} onRetry={refetchTrends} />
            ) : (
              <SentimentTrendChart
                data={trendsData?.trends ?? []}
                loading={loadingTrends}
              />
            )}
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Aspect Sentiment</CardTitle>
            <CardDescription>
              How each aspect performs across all entities
            </CardDescription>
          </CardHeader>
          <CardContent>
            {aspectsError ? (
              <DataError message={aspectsError} onRetry={refetchAspects} />
            ) : (
              <AspectBarChart
                data={aspectsData?.aspects ?? []}
                loading={loadingAspects}
              />
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>Facebook Engagement</CardTitle>
          <CardDescription>
            Reaction breakdown and engagement metrics for Facebook pages
          </CardDescription>
        </CardHeader>
        <CardContent>
          {engagementError ? (
            <DataError message={engagementError} onRetry={refetchEngagement} />
          ) : (
            <EngagementChart
              data={engagementData?.engagement ?? []}
              loading={loadingEngagement}
            />
          )}
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>Entity Comparison</CardTitle>
          <CardDescription>
            Compare sentiment profiles across entities
          </CardDescription>
        </CardHeader>
        <CardContent>
          {entitiesError ? (
            <DataError message={entitiesError} onRetry={refetchEntities} />
          ) : (
            <EntityRadar entities={entities} loading={loadingEntities} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
