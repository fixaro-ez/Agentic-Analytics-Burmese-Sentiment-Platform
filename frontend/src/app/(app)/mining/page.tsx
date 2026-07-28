"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function MiningPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Data Mining</h1>
        <p className="text-muted-foreground">
          Association rules and entity clustering results.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Association Rules</CardTitle>
            <CardDescription>
              Apriori-discovered correlations between ABSA aspects
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                TODO(Member 3): Table of rules with antecedent, consequent,
                support, confidence, lift. Fetch GET /api/mining/association-rules.
                Sort by lift descending. Highlight strong rules.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Entity Clusters</CardTitle>
            <CardDescription>
              K-Means clustering of entities by sentiment profile
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                TODO(Member 3): Cluster visualization (table or scatter).
                Fetch GET /api/mining/clusters.
                Show cluster_id, entities, centroid features.
                Color-code clusters by performance level.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
