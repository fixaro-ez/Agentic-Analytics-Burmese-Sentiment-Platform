"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Alerts</h1>
        <p className="text-muted-foreground">
          AI-detected sentiment anomalies and PR crisis warnings.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Alerts</CardTitle>
          <CardDescription>Sentiment spikes and negative surges detected by the AI monitor</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed">
            <p className="text-sm text-muted-foreground">
              TODO(Member 5): Alert list with severity badges.
              Fetch GET /api/alerts. Display alert_type, severity (Badge), message, created_at.
              Add filter: acknowledged/unacknowledged.
              Add acknowledge button — POST /api/alerts/:id/acknowledge.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alert Configuration</CardTitle>
          <CardDescription>Configure thresholds for sentiment anomaly detection</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
            <p className="text-sm text-muted-foreground">
              TODO(Member 5): Config form with:
              negative_threshold (slider), spike_window_hours (number), spike_zscore (number).
              POST /api/alerts/config.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
