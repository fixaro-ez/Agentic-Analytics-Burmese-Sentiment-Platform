"use client"

import { useState } from "react"

import { BenchmarkPanel } from "@/components/analytics/benchmark-panel"
import { AspectBarChart } from "@/components/charts/aspect-bar-chart"
import { EngagementChart } from "@/components/charts/engagement-chart"
import { SentimentTrendChart } from "@/components/charts/sentiment-trend-chart"
import { AspectRadarPanel } from "@/components/dashboard/aspect-radar-panel"
import { DataError } from "@/components/data-error"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import {
  useAspectBreakdown,
  useEntitySentiments,
  useFacebookEngagement,
  useSentimentTrendsFiltered,
} from "@/hooks/use-analytics"
import { myanmarLangProps } from "@/lib/myanmar"
import { useFilterStore } from "@/lib/stores/filters"

type AnalyticsView = "overview" | "benchmark"

export default function AnalyticsPage() {
  const entityId = useFilterStore((state) => state.entityId)
  const days = useFilterStore((state) => state.days)
  const [view, setView] = useState<AnalyticsView>("overview")

  const {
    data: entitiesData,
    error: entitiesError,
    refetch: refetchEntities,
  } = useEntitySentiments()
  const {
    data: trendsData,
    loading: loadingTrends,
    error: trendsError,
    refetch: refetchTrends,
  } = useSentimentTrendsFiltered(entityId ?? undefined, days)
  const {
    data: aspectsData,
    loading: loadingAspects,
    error: aspectsError,
    refetch: refetchAspects,
  } = useAspectBreakdown(entityId, days)
  const {
    data: engagementData,
    loading: loadingEngagement,
    error: engagementError,
    refetch: refetchEngagement,
  } = useFacebookEngagement(entityId, days)

  const entities = (entitiesData?.entities ?? []).filter(
    (entity) => entity.total_reviews > 0
  )
  const selectedEntityName =
    entityId != null
      ? entities.find((entity) => entity.entity_id === entityId)?.entity_name ??
        "selected entity"
      : null

  return (
    <Tabs
      value={view}
      onValueChange={(value) => setView(value as AnalyticsView)}
      className="space-y-6 pb-20"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
          <p className="text-muted-foreground">
            Explore sentiment performance or compare one mapped brand against
            one competitor.
          </p>
        </div>
        <TabsList aria-label="Analytics view">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="benchmark">Benchmark</TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="overview" className="mt-0 space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>Weekly sentiment balance</CardTitle>
              <CardDescription>
                Positive and neutral above zero; negative below
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Showing last {days} days
                {selectedEntityName != null ? (
                  <>
                    {" for "}
                    <span {...myanmarLangProps(selectedEntityName)}>
                      {selectedEntityName}
                    </span>
                  </>
                ) : (
                  " for all entities"
                )}
                {" — change via the filter bar above."}
              </p>
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
              <CardTitle>Aspect sentiment mix</CardTitle>
              <CardDescription>
                Compare positive, neutral, and negative shares
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
            <CardTitle>Facebook engagement</CardTitle>
            <CardDescription>
              Reaction breakdown and engagement metrics for Facebook pages
            </CardDescription>
          </CardHeader>
          <CardContent>
            {engagementError ? (
              <DataError
                message={engagementError}
                onRetry={refetchEngagement}
              />
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
            <CardTitle>Entity comparison</CardTitle>
            <CardDescription>
              Compare sentiment profiles across the active entity selection
            </CardDescription>
          </CardHeader>
          <CardContent>
            {entitiesError ? (
              <DataError message={entitiesError} onRetry={refetchEntities} />
            ) : (
              <AspectRadarPanel />
            )}
          </CardContent>
        </Card>

      </TabsContent>

      <TabsContent value="benchmark" className="mt-0">
        <BenchmarkPanel />
      </TabsContent>
    </Tabs>
  )
}
