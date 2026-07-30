"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
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

type PlatformFilter = "all" | "facebook" | "foodpanda"

export default function EntitiesPage() {
  const { data, loading, error } = useEntitySentiments()
  const [filter, setFilter] = useState<PlatformFilter>("all")
  const router = useRouter()

  const entities = data?.entities ?? []
  const filtered = filter === "all"
    ? entities
    : entities.filter((e) => e.platform.toLowerCase() === filter)

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
                onClick={() => setFilter(f)}
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
                  <TableHead className="text-right">Reviews</TableHead>
                  <TableHead className="text-right">Positive %</TableHead>
                  <TableHead className="text-right">Negative %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((e) => (
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
                    <TableCell>
                      <Badge variant={e.platform === "facebook" ? "default" : "secondary"}>
                        {e.platform}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">{e.total_reviews}</TableCell>
                    <TableCell className="text-right text-green-600">
                      {e.positive_ratio != null
                        ? `${(e.positive_ratio * 100).toFixed(1)}%`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right text-red-600">
                      {e.negative_ratio != null
                        ? `${(e.negative_ratio * 100).toFixed(1)}%`
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
                {filter === "all" ? "No entities found" : `No ${filter} entities found`}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
