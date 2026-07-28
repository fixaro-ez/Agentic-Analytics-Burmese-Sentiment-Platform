"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground">
          Deep-dive into sentiment trends, aspect analysis, and engagement metrics.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Sentiment Over Time</CardTitle>
            <CardDescription>Track positive, neutral, and negative sentiment trends</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex h-72 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                TODO(Member 4): Recharts AreaChart with time range picker.
                Fetch GET /api/analytics/trends?days=30.
                Add entity filter dropdown.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Aspect Sentiment</CardTitle>
            <CardDescription>How each aspect performs across all entities</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex h-72 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">
                TODO(Member 4): Stacked BarChart grouped by aspect_category.
                Fetch GET /api/analytics/aspects.
                Color code: green=Positive, gray=Neutral, red=Negative.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Facebook Engagement</CardTitle>
          <CardDescription>Reaction breakdown and engagement metrics for Facebook pages</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
            <p className="text-sm text-muted-foreground">
              TODO(Member 4): BarChart of reactions (like, love, care, haha, wow, sad, angry).
              Fetch GET /api/analytics/engagement.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Entity Comparison</CardTitle>
          <CardDescription>Compare sentiment profiles across entities</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
            <p className="text-sm text-muted-foreground">
              TODO(Member 4): RadarChart comparing entities on 6 aspects.
              Fetch GET /api/analytics/entities.
              Use ASPECT_LABELS from lib/types.ts for display names.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
