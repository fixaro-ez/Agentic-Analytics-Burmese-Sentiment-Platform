"use client"

import { useState } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useEntitySentiments } from "@/hooks/use-analytics"
import { myanmarLangProps } from "@/lib/myanmar"
import { paginate } from "@/lib/pagination"
import { BrandMappingSettings } from "@/components/analytics/brand-mapping-settings"

type PlatformFilter = "all" | "facebook" | "foodpanda"
const ENTITY_PAGE_SIZE = 5

export default function EntitiesPage() {
  const { data, loading, error } = useEntitySentiments()
  const [filter, setFilter] = useState<PlatformFilter>("all")
  const [requestedPage, setRequestedPage] = useState(0)

  const entities = data?.entities ?? []
  const filtered = filter === "all"
    ? entities
    : entities.filter((e) => e.platform.toLowerCase() === filter)
  const pagination = paginate(filtered, requestedPage, ENTITY_PAGE_SIZE)

  const changeFilter = (nextFilter: PlatformFilter) => {
    setFilter(nextFilter)
    setRequestedPage(0)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Entities</h1>
        <p className="text-muted-foreground">
          Manage tracked Facebook pages and Foodpanda shops.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Entities</CardTitle>
          <CardDescription>Facebook pages and Foodpanda shops being tracked</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 mb-4">
            {(["all", "facebook", "foodpanda"] as PlatformFilter[]).map((f) => (
              <Button
                key={f}
                variant={filter === f ? "default" : "outline"}
                size="sm"
                aria-pressed={filter === f}
                onClick={() => changeFilter(f)}
              >
                {f === "all" ? "All" : f === "facebook" ? "Facebook" : "Foodpanda"}
              </Button>
            ))}
          </div>

          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          ) : filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Entity</TableHead>
                  <TableHead>Platform</TableHead>
                  <TableHead className="text-right">Data</TableHead>
                  <TableHead className="text-right">Engagement</TableHead>
                  <TableHead className="text-right">Positive %</TableHead>
                  <TableHead className="text-right">Negative %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pagination.items.map((e) => (
                  <TableRow
                    key={e.entity_id}
                    className="hover:bg-muted/40"
                  >
                    <TableCell
                      className="font-medium"
                      {...myanmarLangProps(e.entity_name)}
                    >
                      <Link
                        href={`/entities/${e.entity_id}`}
                        className="inline-flex min-h-11 items-center text-primary underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {e.entity_name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge variant={e.platform === "facebook" ? "default" : "secondary"}>
                        {e.platform}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {e.platform === "facebook"
                        ? `${e.total_posts.toLocaleString()} posts`
                        : `${e.total_reviews.toLocaleString()} reviews`}
                    </TableCell>
                    <TableCell className="text-right">
                      {e.platform === "facebook" && e.total_reactions != null
                        ? `${e.total_reactions.toLocaleString()} reactions`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right text-sentiment-positive-foreground">
                      {e.positive_ratio != null
                        ? `${(e.positive_ratio * 100).toFixed(1)}%`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right text-sentiment-negative-foreground">
                      {e.negative_ratio != null
                        ? `${(e.negative_ratio * 100).toFixed(1)}%`
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

              {pagination.pageCount > 1 && (
                <nav
                  aria-label="Entity pages"
                  className="flex flex-wrap items-center justify-between gap-3 border-t pt-4"
                >
                  <p
                    className="text-sm text-muted-foreground"
                    aria-live="polite"
                  >
                    {pagination.rangeStart}{"\u2013"}{pagination.rangeEnd} of {pagination.total}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={pagination.page === 0}
                      onClick={() => setRequestedPage(pagination.page - 1)}
                    >
                      Previous
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={pagination.page >= pagination.pageCount - 1}
                      onClick={() => setRequestedPage(pagination.page + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </nav>
              )}
            </div>
          ) : (
            <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                {filter === "all" ? "No entities found" : `No ${filter} entities found`}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <BrandMappingSettings entities={entities} />
    </div>
  )
}
