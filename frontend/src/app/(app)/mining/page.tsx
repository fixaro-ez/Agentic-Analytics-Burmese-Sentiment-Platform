"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DataError } from "@/components/data-error"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useApi } from "@/hooks/use-api"
import type { AssociationRule, EntityCluster } from "@/lib/types"
import { ASPECT_LABELS } from "@/lib/types"

const percent = (value: number) => `${(value * 100).toFixed(1)}%`

export default function MiningPage() {
  const rules = useApi<{ rules: AssociationRule[] }>("/api/mining/association-rules")
  const clusters = useApi<{ clusters: EntityCluster[] }>("/api/mining/clusters")

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Data Mining</h1>
        <p className="text-muted-foreground">
          Discover aspect relationships and interpretable entity performance groups.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Association Rules</CardTitle>
          <CardDescription>
            Aspects that frequently appear together in the same feedback
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rules.loading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-10 w-full" />
              ))}
            </div>
          ) : rules.error ? (
            <DataError message={rules.error} onRetry={rules.refetch} />
          ) : rules.data?.rules.length ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When feedback mentions</TableHead>
                    <TableHead>It also mentions</TableHead>
                    <TableHead className="text-right">Support</TableHead>
                    <TableHead className="text-right">Confidence</TableHead>
                    <TableHead className="text-right">Lift</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rules.data.rules.map((rule, index) => (
                    <TableRow key={`${rule.antecedent.join("-")}-${rule.consequent.join("-")}-${index}`}>
                      <TableCell>{rule.antecedent.map((item) => ASPECT_LABELS[item] ?? item).join(", ")}</TableCell>
                      <TableCell>{rule.consequent.map((item) => ASPECT_LABELS[item] ?? item).join(", ")}</TableCell>
                      <TableCell className="text-right">{percent(rule.support)}</TableCell>
                      <TableCell className="text-right">{percent(rule.confidence)}</TableCell>
                      <TableCell className="text-right font-medium">{rule.lift.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
              More feedback with multiple aspects is needed to produce reliable rules.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Entity Segments</CardTitle>
          <CardDescription>
            Transparent groupings based on positive and negative sentiment ratios
          </CardDescription>
        </CardHeader>
        <CardContent>
          {clusters.loading ? (
            <div className="grid gap-3 md:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-40 w-full" />
              ))}
            </div>
          ) : clusters.error ? (
            <DataError message={clusters.error} onRetry={clusters.refetch} />
          ) : clusters.data?.clusters.length ? (
            <div className="grid gap-4 md:grid-cols-3">
              {clusters.data.clusters.map((cluster) => (
                <section key={cluster.cluster_id} className="rounded-lg border p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="font-semibold">{cluster.label}</h2>
                    <Badge variant={cluster.cluster_id === 2 ? "destructive" : "secondary"}>
                      {cluster.entities.length}
                    </Badge>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-muted-foreground">Positive</dt>
                      <dd className="font-medium">{percent(cluster.centroid.positive_ratio)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Negative</dt>
                      <dd className="font-medium">{percent(cluster.centroid.negative_ratio)}</dd>
                    </div>
                  </dl>
                  <ul className="mt-4 space-y-2">
                    {cluster.entities.map((entity) => (
                      <li key={entity.entity_id} className="rounded-md bg-muted/60 px-3 py-2 text-sm">
                        <span className="font-medium">{entity.entity_name}</span>
                        <span className="ml-2 text-muted-foreground">{entity.total_reviews} reviews</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
              No entity sentiment profiles are available yet.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
