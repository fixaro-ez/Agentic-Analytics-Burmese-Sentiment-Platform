"use client"

import { useState } from "react"

import { DataError } from "@/components/data-error"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useEntityReviews } from "@/hooks/use-analytics"
import { myanmarLangProps } from "@/lib/myanmar"
import { ASPECT_LABELS, type EntityReview } from "@/lib/types"

const PAGE_SIZE = 10

function ReviewItem({
  review,
  selected = false,
}: {
  review: EntityReview
  selected?: boolean
}) {
  return (
    <article
      id={selected ? "selected-review" : undefined}
      className={
        selected
          ? "scroll-mt-40 rounded-lg bg-primary/5 p-4 ring-1 ring-primary/40"
          : "rounded-lg border p-4"
      }
    >
      <p
        className="break-words text-sm leading-6"
        {...myanmarLangProps(review.review_text)}
      >
        {review.review_text || "No review text"}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {review.sentiment_label && (
          <Badge
            variant={
              review.sentiment_label === "Positive"
                ? "default"
                : review.sentiment_label === "Negative"
                  ? "destructive"
                  : "secondary"
            }
            className="text-xs"
          >
            {review.sentiment_label}
          </Badge>
        )}
        {review.confidence_score != null && (
          <span>{(review.confidence_score * 100).toFixed(0)}% confident</span>
        )}
        {review.aspect_category && (
          <span>
            {ASPECT_LABELS[review.aspect_category] ?? review.aspect_category}
          </span>
        )}
        {review.created_at && <span>{review.created_at}</span>}
      </div>
    </article>
  )
}

export function EntityReviewBrowser({
  entityId,
  days,
  aspect,
  focusFeedbackId,
}: {
  entityId: number
  days: number
  aspect: string | null
  focusFeedbackId: string | null
}) {
  const [cursorTrail, setCursorTrail] = useState<(string | null)[]>([null])
  const pageIndex = cursorTrail.length - 1
  const cursor = cursorTrail[pageIndex]
  const { data, loading, error, refetch } = useEntityReviews(
    entityId,
    days,
    aspect,
    cursor,
    focusFeedbackId
  )
  const focusReview = data?.focus_review ?? null
  const reviews =
    data?.reviews.filter(
      (review) => review.feedback_id !== focusReview?.feedback_id
    ) ?? []
  const rangeStart = data?.total ? pageIndex * PAGE_SIZE + 1 : 0
  const rangeEnd = data
    ? Math.min(pageIndex * PAGE_SIZE + data.reviews.length, data.total)
    : 0
  const aspectLabel = aspect ? ASPECT_LABELS[aspect] ?? aspect : null

  return (
    <Card id="reviews" className="scroll-mt-36">
      <CardHeader>
        <CardTitle>Reviews</CardTitle>
        <CardDescription>
          {data
            ? `${data.total} ${aspectLabel ? `${aspectLabel} ` : ""}reviews in the last ${days} days`
            : `Reviews from the last ${days} days`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {error ? (
          <DataError message={error} onRetry={refetch} />
        ) : loading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-20 w-full" />
            ))}
          </div>
        ) : (
          <>
            {focusFeedbackId && focusReview && (
              <ReviewItem review={focusReview} selected />
            )}

            {focusFeedbackId && !focusReview && (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                The selected review is no longer available for this entity and
                aspect.
              </div>
            )}

            {reviews.length > 0 ? (
              <div className="space-y-3">
                {reviews.map((review) => (
                  <ReviewItem key={review.feedback_id} review={review} />
                ))}
              </div>
            ) : !focusReview ? (
              <div className="flex h-40 items-center justify-center rounded-md border border-dashed">
                <p className="text-sm text-muted-foreground">
                  {aspectLabel
                    ? `No ${aspectLabel} reviews found in this date range`
                    : "No reviews found in this date range"}
                </p>
              </div>
            ) : null}

            {data && data.total > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                <p className="text-sm text-muted-foreground">
                  {rangeStart}–{rangeEnd} of {data.total}
                </p>
                <div className="flex gap-2" aria-label="Review pages">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={pageIndex === 0}
                    onClick={() =>
                      setCursorTrail((trail) => trail.slice(0, -1))
                    }
                  >
                    Previous
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!data.next_cursor}
                    onClick={() =>
                      data.next_cursor &&
                      setCursorTrail((trail) => [...trail, data.next_cursor])
                    }
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
