"use client"

import { useMemo } from "react"
import { useRouter } from "next/navigation"
import { AspectBreakdownPanel } from "@/components/dashboard/aspect-breakdown-panel"
import { AspectRadarPanel } from "@/components/dashboard/aspect-radar-panel"
import { KpiStrip } from "@/components/dashboard/kpi-strip"
import { PinnedChatInsights } from "@/components/dashboard/pinned-chat-insights"
import { SocialEngagementPanel } from "@/components/dashboard/social-engagement-panel"
import { TopDriversPanel } from "@/components/dashboard/top-drivers-panel"
import { SentimentTrendChart } from "@/components/charts/sentiment-trend-chart"
import { DataError } from "@/components/data-error"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  useEntitySentiments,
  useSentimentTrendsFiltered,
} from "@/hooks/use-analytics"
import { myanmarLangProps } from "@/lib/myanmar"
import { useFilterStore } from "@/lib/stores/filters"

export default function DashboardPage() {
  const router = useRouter()
  const entityId = useFilterStore((state) => state.entityId)
  const days = useFilterStore((state) => state.days)
  const setEntity = useFilterStore((state) => state.setEntity)

  const trends = useSentimentTrendsFiltered(entityId ?? undefined, days)
  const entities = useEntitySentiments()

  const visibleEntities = useMemo(() => {
    const rows = entities.data?.entities ?? []
    return entityId != null
      ? rows.filter((entity) => entity.entity_id === entityId)
      : rows
  }, [entities.data, entityId])

  return (
    <div className="space-y-6 pb-20">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Sentiment, aspect, and engagement signals for the active entity and
          date filters.
        </p>
      </div>

      <KpiStrip />
      <PinnedChatInsights />

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.85fr)_minmax(320px,1fr)]">
        <Card id="panel-trends" className="min-w-0 scroll-mt-36">
          <CardHeader>
            <CardTitle>Weekly sentiment balance</CardTitle>
            <CardDescription>
              Positive and neutral above zero; negative below
            </CardDescription>
          </CardHeader>
          <CardContent className="min-w-0">
            {trends.error ? (
              <DataError message={trends.error} onRetry={trends.refetch} />
            ) : (
              <SentimentTrendChart
                data={trends.data?.trends ?? []}
                loading={trends.loading}
              />
            )}
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Aspect health radar</CardTitle>
            <CardDescription>
              Six ABSA dimensions with optional entity comparison
            </CardDescription>
          </CardHeader>
          <CardContent className="min-w-0">
            <AspectRadarPanel />
          </CardContent>
        </Card>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.85fr)_minmax(320px,1fr)]">
        <Card id="panel-aspects" className="min-w-0 scroll-mt-36">
          <CardHeader>
            <CardTitle>Aspect sentiment mix</CardTitle>
            <CardDescription>
              Compare percentages; select an aspect to filter reviews
            </CardDescription>
          </CardHeader>
          <CardContent className="min-w-0">
            <AspectBreakdownPanel />
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Top drivers</CardTitle>
            <CardDescription>
              Negative-weighted aspects and recently flagged feedback
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TopDriversPanel />
          </CardContent>
        </Card>
      </div>

      <Card id="panel-engagement" className="min-w-0 scroll-mt-36">
        <CardHeader>
          <CardTitle>Social engagement</CardTitle>
          <CardDescription>
            Facebook reaction mix and positivity, negativity, and haha ratios
          </CardDescription>
        </CardHeader>
        <CardContent className="min-w-0">
          <SocialEngagementPanel />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Entity performance</CardTitle>
          <CardDescription>
            Active entity, or all entities when no entity filter is set
          </CardDescription>
        </CardHeader>
        <CardContent>
          {entities.error ? (
            <DataError message={entities.error} onRetry={entities.refetch} />
          ) : entities.loading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-10 w-full" />
              ))}
            </div>
          ) : visibleEntities.length ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Entity</TableHead>
                    <TableHead>Platform</TableHead>
                    <TableHead className="text-right">Data</TableHead>
                    <TableHead className="text-right">Engagement</TableHead>
                    <TableHead className="text-right">Positive</TableHead>
                    <TableHead className="text-right">Negative</TableHead>
                    <TableHead className="text-right">Positive %</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleEntities.map((entity) => (
                    <TableRow
                      key={entity.entity_id}
                      className="cursor-pointer"
                      role="button"
                      tabIndex={0}
                      onClick={() => {
                        setEntity(entity.entity_id)
                        router.push(`/entities/${entity.entity_id}`)
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault()
                          setEntity(entity.entity_id)
                          router.push(`/entities/${entity.entity_id}`)
                        }
                      }}
                    >
                      <TableCell
                        className="font-medium"
                        {...myanmarLangProps(entity.entity_name)}
                      >
                        {entity.entity_name}
                      </TableCell>
                      <TableCell>{entity.platform}</TableCell>
                      <TableCell className="text-right">
                        {entity.platform === "facebook"
                          ? `${entity.total_posts.toLocaleString()} posts`
                          : `${entity.total_reviews.toLocaleString()} reviews`}
                      </TableCell>
                      <TableCell className="text-right">
                        {entity.platform === "facebook" &&
                        entity.total_reactions != null
                          ? `${entity.total_reactions.toLocaleString()} reactions`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {entity.total_reviews > 0
                          ? entity.positive_count.toLocaleString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {entity.total_reviews > 0
                          ? entity.negative_count.toLocaleString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {entity.positive_ratio != null
                          ? `${(entity.positive_ratio * 100).toFixed(1)}%`
                          : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                No entity data matches the active filters.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

    </div>
  )
}
