"use client"

import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SentimentTrendChart } from "@/components/charts/sentiment-trend-chart"
import { DataError } from "@/components/data-error"
import {
  useSentimentOverview,
  useEntitySentiments,
  useAspectBreakdown,
  useSentimentTrends,
} from "@/hooks/use-analytics"
import { ASPECT_LABELS } from "@/lib/types"

export default function DashboardPage() {
  const {
    data: overview,
    loading: loadingOverview,
    error: overviewError,
    refetch: refetchOverview,
  } = useSentimentOverview()
  const {
    data: entitiesData,
    loading: loadingEntities,
    error: entitiesError,
    refetch: refetchEntities,
  } = useEntitySentiments()
  const {
    data: aspectsData,
    loading: loadingAspects,
    error: aspectsError,
    refetch: refetchAspects,
  } = useAspectBreakdown()
  const {
    data: trendsData,
    loading: loadingTrends,
    error: trendsError,
    refetch: refetchTrends,
  } = useSentimentTrends()
  const router = useRouter()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of Burmese sentiment analytics across all entities.
        </p>
      </div>

      {overviewError && (
        <DataError message={overviewError} onRetry={refetchOverview} />
      )}

      {/* ---- KPI Cards ---- */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Reviews</CardDescription>
            {loadingOverview ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <CardTitle className="text-2xl">
                {overview?.total_reviews?.toLocaleString() ?? "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Positive Ratio</CardDescription>
            {loadingOverview ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <CardTitle className="text-2xl text-green-600">
                {overview?.positive_ratio != null
                  ? `${(overview.positive_ratio * 100).toFixed(1)}%`
                  : "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Negative Ratio</CardDescription>
            {loadingOverview ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <CardTitle className="text-2xl text-red-600">
                {overview?.negative_ratio != null
                  ? `${(overview.negative_ratio * 100).toFixed(1)}%`
                  : "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Avg Confidence</CardDescription>
            {loadingOverview ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <CardTitle className="text-2xl">
                {overview?.avg_confidence != null
                  ? `${(overview.avg_confidence * 100).toFixed(1)}%`
                  : "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>
      </div>

      {/* ---- Charts Row ---- */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Sentiment Trend</CardTitle>
            <CardDescription>Daily sentiment counts over time</CardDescription>
          </CardHeader>
          <CardContent>
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

        <Card>
          <CardHeader>
            <CardTitle>Aspect Breakdown</CardTitle>
            <CardDescription>Sentiment distribution across ABSA aspects</CardDescription>
          </CardHeader>
          <CardContent>
            {aspectsError ? (
              <DataError message={aspectsError} onRetry={refetchAspects} />
            ) : loadingAspects ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : aspectsData?.aspects && aspectsData.aspects.length > 0 ? (
              <div className="space-y-3">
                {(() => {
                  const maxCount = Math.max(...aspectsData.aspects.map((a) => a.count), 1)
                  return aspectsData.aspects.map((a) => (
                  <div key={`${a.aspect}-${a.sentiment}`} className="flex items-center gap-3">
                    <span className="w-48 truncate text-sm" title={ASPECT_LABELS[a.aspect] ?? a.aspect}>
                      {ASPECT_LABELS[a.aspect] ?? a.aspect}
                    </span>
                    <span
                      className={`inline-block h-3 rounded ${
                        a.sentiment.toLowerCase() === "positive"
                          ? "bg-green-500 dark:bg-green-600"
                          : a.sentiment.toLowerCase() === "negative"
                          ? "bg-red-500 dark:bg-red-600"
                          : "bg-yellow-400 dark:bg-yellow-500"
                      }`}
                      style={{ width: `${(a.count / maxCount) * 200}px` }}
                    />
                    <span className="text-xs text-muted-foreground">
                      {a.sentiment} ({a.count})
                    </span>
                  </div>
                  ))
                })()}
              </div>
            ) : (
              <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
                <p className="text-sm text-muted-foreground">No aspect data available</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ---- Entity Performance Table ---- */}
      <Card>
        <CardHeader>
          <CardTitle>Entity Performance</CardTitle>
          <CardDescription>Sentiment overview per entity</CardDescription>
        </CardHeader>
        <CardContent>
          {entitiesError ? (
            <DataError message={entitiesError} onRetry={refetchEntities} />
          ) : loadingEntities ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : entitiesData?.entities && entitiesData.entities.length > 0 ? (
            <div className="overflow-x-auto">
              <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Entity</TableHead>
                  <TableHead>Platform</TableHead>
                  <TableHead className="text-right">Reviews</TableHead>
                  <TableHead className="text-right">Positive</TableHead>
                  <TableHead className="text-right">Negative</TableHead>
                  <TableHead className="text-right">Positive %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entitiesData.entities.map((e) => (
                  <TableRow
                    key={e.entity_id}
                    className="cursor-pointer"
                    role="button"
                    tabIndex={0}
                    onClick={() => router.push(`/entities/${e.entity_id}`)}
                    onKeyDown={(ev) => {
                      if (ev.key === "Enter" || ev.key === " ") {
                        ev.preventDefault()
                        router.push(`/entities/${e.entity_id}`)
                      }
                    }}
                  >
                    <TableCell className="font-medium">{e.entity_name}</TableCell>
                    <TableCell>{e.platform}</TableCell>
                    <TableCell className="text-right">{e.total_reviews}</TableCell>
                    <TableCell className="text-right">{e.positive_count}</TableCell>
                    <TableCell className="text-right">{e.negative_count}</TableCell>
                    <TableCell className="text-right">
                      {e.positive_ratio != null
                        ? `${(e.positive_ratio * 100).toFixed(1)}%`
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          ) : (
            <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">No entity data available</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
