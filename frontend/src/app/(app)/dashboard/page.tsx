"use client"

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
import {
  useSentimentOverview,
  useEntitySentiments,
  useAspectBreakdown,
  useSentimentTrends,
} from "@/hooks/use-analytics"
import { ASPECT_LABELS } from "@/lib/types"

export default function DashboardPage() {
  const { data: overview, loading: loadingOverview } = useSentimentOverview()
  const { data: entitiesData, loading: loadingEntities } = useEntitySentiments()
  const { data: aspectsData, loading: loadingAspects } = useAspectBreakdown()
  const { data: trendsData, loading: loadingTrends } = useSentimentTrends()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of Burmese sentiment analytics across all entities.
        </p>
      </div>

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
            <SentimentTrendChart
              data={trendsData?.trends ?? []}
              loading={loadingTrends}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Aspect Breakdown</CardTitle>
            <CardDescription>Sentiment distribution across ABSA aspects</CardDescription>
          </CardHeader>
          <CardContent>
            {loadingAspects ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : aspectsData?.aspects && aspectsData.aspects.length > 0 ? (
              <div className="space-y-3">
                {aspectsData.aspects.map((a) => (
                  <div key={`${a.aspect}-${a.sentiment}`} className="flex items-center gap-3">
                    <span className="w-48 truncate text-sm" title={ASPECT_LABELS[a.aspect] ?? a.aspect}>
                      {ASPECT_LABELS[a.aspect] ?? a.aspect}
                    </span>
                    <span
                      className={`inline-block h-3 rounded ${
                        a.sentiment === "positive"
                          ? "bg-green-500"
                          : a.sentiment === "negative"
                          ? "bg-red-500"
                          : "bg-yellow-400"
                      }`}
                      style={{ width: `${Math.min((a.count / (overview?.total_reviews || 1)) * 200, 200)}px` }}
                    />
                    <span className="text-xs text-muted-foreground">
                      {a.sentiment} ({a.count})
                    </span>
                  </div>
                ))}
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
          {loadingEntities ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : entitiesData?.entities && entitiesData.entities.length > 0 ? (
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
                  <TableRow key={e.entity_id}>
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
