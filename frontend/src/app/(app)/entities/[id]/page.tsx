"use client"

import { useParams, useSearchParams } from "next/navigation"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import { EntityReviewBrowser } from "@/components/entities/entity-review-browser"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DataError } from "@/components/data-error"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useEntityDetail } from "@/hooks/use-analytics"
import { ASPECT_LABELS } from "@/lib/types"
import { myanmarLangProps } from "@/lib/myanmar"
import { useFilterStore } from "@/lib/stores/filters"

export default function EntityDetailPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const entityId = Number(params.id)
  const aspect = useFilterStore((state) => state.aspect)
  const days = useFilterStore((state) => state.days)
  const focusFeedbackId = searchParams.get("review")
  const { data, loading, error, refetch } = useEntityDetail(entityId)

  if (isNaN(entityId)) {
    return (
      <div className="space-y-6">
        <Button asChild variant="ghost" size="sm">
          <Link href="/entities">
            <ArrowLeft className="h-4 w-4 mr-2" aria-hidden="true" />
            Back to Entities
          </Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Invalid entity</h1>
        <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
          <p className="text-sm text-destructive">Invalid entity ID</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Button asChild variant="ghost" size="sm">
          <Link href="/entities">
            <ArrowLeft className="h-4 w-4 mr-2" aria-hidden="true" />
            Back to Entities
          </Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Entity details unavailable</h1>
        <DataError message={error} onRetry={refetch} />
      </div>
    )
  }

  const aspectGroups = data?.aspects.reduce((acc, item) => {
    if (!acc[item.aspect_category]) acc[item.aspect_category] = []
    acc[item.aspect_category].push(item)
    return acc
  }, {} as Record<string, typeof data.aspects>) ?? {}
  const isFacebook = data?.platform === "facebook"

  return (
    <div className="space-y-6 pb-24">
      <div className="flex items-center gap-4">
        <Button asChild variant="ghost" size="icon">
          <Link href="/entities">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">Back to entities</span>
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {loading ? (
                <Skeleton className="h-8 w-48" />
              ) : (
                <span {...myanmarLangProps(data?.entity_name)}>
                  {data?.entity_name}
                </span>
              )}
            </h1>
            {data && (
              <Badge variant={data.platform === "facebook" ? "default" : "secondary"}>
                {data.platform}
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground text-sm mt-1">Entity detail overview</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{isFacebook ? "Total Posts" : "Total Reviews"}</CardDescription>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <CardTitle className="text-2xl">
                {(isFacebook ? data?.total_posts : data?.total_reviews)?.toLocaleString() ?? "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{isFacebook ? "Total Reactions" : "Positive Ratio"}</CardDescription>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : isFacebook ? (
              <CardTitle className="text-2xl">
                {data?.total_reactions?.toLocaleString() ?? "—"}
              </CardTitle>
            ) : (
              <CardTitle className="text-2xl text-sentiment-positive-foreground">
                {data?.positive_ratio != null
                  ? `${(data.positive_ratio * 100).toFixed(1)}%`
                  : "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{isFacebook ? "Total Shares" : "Negative Ratio"}</CardDescription>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : isFacebook ? (
              <CardTitle className="text-2xl">
                {data?.total_shares?.toLocaleString() ?? "—"}
              </CardTitle>
            ) : (
              <CardTitle className="text-2xl text-sentiment-negative-foreground">
                {data?.negative_ratio != null
                  ? `${(data.negative_ratio * 100).toFixed(1)}%`
                  : "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{isFacebook ? "Total Comments" : "Avg Confidence"}</CardDescription>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : isFacebook ? (
              <CardTitle className="text-2xl">
                {data?.total_comments?.toLocaleString() ?? "—"}
              </CardTitle>
            ) : (
              <CardTitle className="text-2xl">
                {data?.avg_confidence != null
                  ? `${(data.avg_confidence * 100).toFixed(1)}%`
                  : "—"}
              </CardTitle>
            )}
          </CardHeader>
        </Card>
      </div>

      {!isFacebook && (
        <>
      <Card>
        <CardHeader>
          <CardTitle>Aspect Sentiment Breakdown</CardTitle>
          <CardDescription>
            Sentiment distribution across the 5 ABSA aspects
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : Object.keys(aspectGroups).length > 0 ? (
            <div className="space-y-4">
              {Object.entries(aspectGroups).map(([aspect, items]) => {
                const total = items.reduce((sum, i) => sum + i.count, 0)
                const positive = items.find((i) => i.sentiment_label === "Positive")?.count ?? 0
                const negative = items.find((i) => i.sentiment_label === "Negative")?.count ?? 0
                const neutral = items.find((i) => i.sentiment_label === "Neutral")?.count ?? 0

                return (
                  <div key={aspect} className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">
                        {ASPECT_LABELS[aspect] ?? aspect}
                      </span>
                      <span className="text-xs text-muted-foreground">{total} reviews</span>
                    </div>
                    <div className="flex h-6 w-full overflow-hidden rounded-md" role="img" aria-label={`${ASPECT_LABELS[aspect] ?? aspect}: ${positive} positive, ${neutral} neutral, ${negative} negative`}>
                      {positive > 0 && (
                        <div
                          className="flex items-center justify-center bg-sentiment-positive text-xs font-medium text-sentiment-on-color"
                          style={{ width: `${(positive / total) * 100}%` }}
                        >
                          {positive}
                        </div>
                      )}
                      {neutral > 0 && (
                        <div
                          className="flex items-center justify-center bg-sentiment-neutral text-xs font-medium text-sentiment-on-color"
                          style={{ width: `${(neutral / total) * 100}%` }}
                        >
                          {neutral}
                        </div>
                      )}
                      {negative > 0 && (
                        <div
                          className="flex items-center justify-center bg-sentiment-negative text-xs font-medium text-sentiment-on-color"
                          style={{ width: `${(negative / total) * 100}%` }}
                        >
                          {negative}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">No aspect data available</p>
            </div>
          )}
        </CardContent>
      </Card>

      <EntityReviewBrowser
        key={`${entityId}-${days}-${aspect ?? "all"}-${focusFeedbackId ?? "none"}`}
        entityId={entityId}
        days={days}
        aspect={aspect}
        focusFeedbackId={focusFeedbackId}
      />
        </>
      )}
    </div>
  )
}
