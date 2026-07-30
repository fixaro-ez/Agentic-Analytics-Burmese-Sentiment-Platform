"use client"

import { FormEvent, useState } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DataError } from "@/components/data-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/use-api"
import { api } from "@/lib/api"
import type { AlertConfig, AlertItem } from "@/lib/types"

export default function AlertsPage() {
  const alerts = useApi<AlertItem[]>("/api/alerts")
  const config = useApi<AlertConfig>("/api/alerts/config")
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setSaving(true)
    setStatus(null)
    try {
      await api.post<AlertConfig>("/api/alerts/config", {
        negative_threshold: Number(form.get("negative_threshold")) / 100,
        spike_window_hours: Number(form.get("spike_window_hours")),
        spike_zscore: Number(form.get("spike_zscore")),
      })
      setStatus("Alert settings saved.")
      config.refetch()
      alerts.refetch()
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Unable to save alert settings")
    } finally {
      setSaving(false)
    }
  }

  async function handleCheck() {
    setChecking(true)
    setStatus(null)
    try {
      await api.post("/api/alerts/check")
      alerts.refetch()
      setStatus("Alert check completed.")
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Unable to run alert check")
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Alerts</h1>
          <p className="text-muted-foreground">
            Monitor entities whose negative sentiment exceeds your threshold.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={handleCheck} disabled={checking}>
          <RefreshCw className={`mr-2 h-4 w-4 ${checking ? "animate-spin" : ""}`} aria-hidden="true" />
          {checking ? "Checking..." : "Check now"}
        </Button>
      </div>

      {status && <p className="text-sm text-muted-foreground" role="status">{status}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Current Alerts</CardTitle>
          <CardDescription>Generated from the latest entity sentiment ratios</CardDescription>
        </CardHeader>
        <CardContent>
          {alerts.loading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-20 w-full" />
              ))}
            </div>
          ) : alerts.error ? (
            <DataError message={alerts.error} onRetry={alerts.refetch} />
          ) : alerts.data && alerts.data.length > 0 ? (
            <div className="space-y-3">
              {alerts.data.map((alert) => (
                <article key={alert.alert_id} className="flex gap-3 rounded-lg border p-4">
                  <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{alert.entity_name ?? "All entities"}</p>
                      <Badge variant={alert.severity === "critical" ? "destructive" : "secondary"}>
                        {alert.severity}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">{alert.message}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="flex h-40 items-center justify-center rounded-md border border-dashed p-6 text-center">
              <p className="text-sm text-muted-foreground">
                No entities currently exceed the configured threshold.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alert Configuration</CardTitle>
          <CardDescription>Set the sensitivity of sentiment anomaly checks</CardDescription>
        </CardHeader>
        <CardContent>
          {config.loading ? (
            <Skeleton className="h-40 w-full" />
          ) : config.error ? (
            <DataError message={config.error} onRetry={config.refetch} />
          ) : (
            <form
              key={JSON.stringify(config.data)}
              className="grid gap-4 sm:grid-cols-3"
              onSubmit={handleSave}
            >
              <div className="space-y-2">
                <Label htmlFor="negative-threshold">Negative threshold (%)</Label>
                <Input
                  id="negative-threshold"
                  name="negative_threshold"
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  defaultValue={(config.data?.negative_threshold ?? 0.3) * 100}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="spike-window">Spike window (hours)</Label>
                <Input
                  id="spike-window"
                  name="spike_window_hours"
                  type="number"
                  min={1}
                  max={720}
                  defaultValue={config.data?.spike_window_hours ?? 24}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="spike-zscore">Spike z-score</Label>
                <Input
                  id="spike-zscore"
                  name="spike_zscore"
                  type="number"
                  min={0.1}
                  max={10}
                  step={0.1}
                  defaultValue={config.data?.spike_zscore ?? 2}
                  required
                />
              </div>
              <div className="sm:col-span-3">
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving..." : "Save settings"}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
