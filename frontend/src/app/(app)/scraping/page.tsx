"use client"

import { useState, useEffect, useCallback } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import type {
  ScrapeRunResponse,
  ScrapeRunStatus,
  ScrapeRunHistory,
  CookieStatus,
} from "@/lib/types"

export default function ScrapingPage() {
  // ---- Form state ----
  const [source, setSource] = useState<"facebook" | "foodpanda" | "blog">("facebook")
  const [url, setUrl] = useState("")
  const [entityName, setEntityName] = useState("")
  const [maxPosts, setMaxPosts] = useState(10)
  const [headless, setHeadless] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ---- Cookie status (Facebook) ----
  const [cookies, setCookies] = useState<CookieStatus | null>(null)

  // ---- Running job polling ----
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [activeStatus, setActiveStatus] = useState<ScrapeRunStatus | null>(null)

  // ---- History ----
  const [history, setHistory] = useState<ScrapeRunHistory[]>([])
  const [loadingHistory, setLoadingHistory] = useState(true)

  // Fetch cookie status on mount (and when source changes to facebook)
  useEffect(() => {
    if (source === "facebook") {
      api.get<CookieStatus>("/api/scraping/cookies").then(setCookies).catch(() => {})
    }
  }, [source])

  // Fetch scrape history
  const fetchHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const data = await api.get<ScrapeRunHistory[]>("/api/scraping/history?limit=20")
      setHistory(data)
    } catch {
      // silently ignore
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  // Poll active run status every 3 seconds
  useEffect(() => {
    if (!activeRunId) return

    const interval = setInterval(async () => {
      try {
        const status = await api.get<ScrapeRunStatus>(
          `/api/scraping/status/${activeRunId}`
        )
        setActiveStatus(status)
        if (status.status === "completed" || status.status === "failed") {
          clearInterval(interval)
          setActiveRunId(null)
          fetchHistory() // refresh history table
        }
      } catch {
        clearInterval(interval)
        setActiveRunId(null)
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [activeRunId, fetchHistory])

  // ---- Submit handler ----
  async function handleStartScrape() {
    if (!url.trim() || !entityName.trim()) {
      setError("URL and Entity name are required.")
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const res = await api.post<ScrapeRunResponse>("/api/scraping/run", {
        source,
        url: url.trim(),
        entity_name: entityName.trim(),
        max_posts: maxPosts,
        headless,
      })
      setActiveRunId(res.run_id)
      setActiveStatus(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start scrape")
    } finally {
      setSubmitting(false)
    }
  }

  function statusBadge(status: string) {
    if (status === "completed")
      return <Badge className="bg-green-100 text-green-800">Completed</Badge>
    if (status === "failed")
      return <Badge className="bg-red-100 text-red-800">Failed</Badge>
    return <Badge className="bg-blue-100 text-blue-800">Running</Badge>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Scraping</h1>
        <p className="text-muted-foreground">
          Trigger Facebook, Foodpanda, or Blog scraping jobs and monitor their progress.
        </p>
      </div>

      {/* ---- Scrape Form ---- */}
      <Card>
        <CardHeader>
          <CardTitle>Start a Scrape</CardTitle>
          <CardDescription>Configure and launch a new scraping job</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Source selector */}
          <div className="space-y-2">
            <Label>Source</Label>
            <div className="flex gap-2">
              {(["facebook", "foodpanda", "blog"] as const).map((s) => (
                <Button
                  key={s}
                  variant={source === s ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSource(s)}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </Button>
              ))}
            </div>
          </div>

          {/* Cookie status (Facebook only) */}
          {source === "facebook" && cookies && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Cookies:</span>
              {cookies.valid ? (
                <Badge className="bg-green-100 text-green-800">
                  Valid — expires {cookies.expires_at?.slice(0, 10)}
                </Badge>
              ) : (
                <Badge className="bg-red-100 text-red-800">{cookies.message}</Badge>
              )}
            </div>
          )}

          {/* URL */}
          <div className="space-y-2">
            <Label htmlFor="scrape-url">URL</Label>
            <Input
              id="scrape-url"
              placeholder={
                source === "facebook"
                  ? "https://www.facebook.com/YourPage"
                  : source === "foodpanda"
                  ? "https://www.foodpanda.com.mm/restaurant/..."
                  : "https://example.com/blog-article"
              }
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>

          {/* Entity name */}
          <div className="space-y-2">
            <Label htmlFor="scrape-entity">Entity Name</Label>
            <Input
              id="scrape-entity"
              placeholder="e.g. KFC Myanmar"
              value={entityName}
              onChange={(e) => setEntityName(e.target.value)}
            />
          </div>

          {/* Max posts (Facebook only) */}
          {source === "facebook" && (
            <div className="space-y-2">
              <Label htmlFor="scrape-max">Max Posts</Label>
              <Input
                id="scrape-max"
                type="number"
                min={1}
                max={200}
                value={maxPosts}
                onChange={(e) => setMaxPosts(parseInt(e.target.value) || 10)}
                className="w-32"
              />
            </div>
          )}

          {/* Headless toggle */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="scrape-headless"
              checked={headless}
              onChange={(e) => setHeadless(e.target.checked)}
              className="h-4 w-4"
            />
            <Label htmlFor="scrape-headless" className="cursor-pointer">
              Run headless (no browser window)
            </Label>
          </div>

          {/* Error */}
          {error && <p className="text-sm text-red-600">{error}</p>}

          {/* Submit */}
          <Button onClick={handleStartScrape} disabled={submitting || !!activeRunId}>
            {submitting ? "Starting..." : activeRunId ? "Running..." : "Start Scrape"}
          </Button>
        </CardContent>
      </Card>

      {/* ---- Active Job Status ---- */}
      {activeRunId && (
        <Card>
          <CardHeader>
            <CardTitle>Running Job</CardTitle>
            <CardDescription>Polling status every 3 seconds</CardDescription>
          </CardHeader>
          <CardContent>
            {activeStatus ? (
              <div className="space-y-2 text-sm">
                <p>
                  <span className="font-medium">Run ID:</span> {activeStatus.run_id}
                </p>
                <p>
                  <span className="font-medium">Source:</span> {activeStatus.source}
                </p>
                <p>
                  <span className="font-medium">Entity:</span> {activeStatus.entity_name}
                </p>
                <p>
                  <span className="font-medium">Status:</span>{" "}
                  {statusBadge(activeStatus.status)}
                </p>
                {activeStatus.error && (
                  <p className="text-red-600">{activeStatus.error}</p>
                )}
              </div>
            ) : (
              <Skeleton className="h-24 w-full" />
            )}
          </CardContent>
        </Card>
      )}

      {/* ---- History Table ---- */}
      <Card>
        <CardHeader>
          <CardTitle>Scrape History</CardTitle>
          <CardDescription>Recent scraping runs</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingHistory ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : history.length === 0 ? (
            <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
              <p className="text-sm text-muted-foreground">No scrape runs yet</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run ID</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Stats</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((h) => (
                  <TableRow key={h.run_id}>
                    <TableCell className="font-mono text-xs">
                      {h.run_id.slice(0, 8)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {h.run_type.replace("scrape_", "")}
                      </Badge>
                    </TableCell>
                    <TableCell>{statusBadge(h.status)}</TableCell>
                    <TableCell className="text-xs">
                      {h.started_at?.slice(0, 19).replace("T", " ")}
                    </TableCell>
                    <TableCell>
                      {h.duration_seconds != null
                        ? `${h.duration_seconds.toFixed(1)}s`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-xs">
                      {h.stats
                        ? JSON.stringify(
                            Object.fromEntries(
                              Object.entries(h.stats).filter(([k]) => k !== "duration" && k !== "source" && k !== "url" && k !== "entity_name")
                            )
                          )
                        : h.error
                        ? `Error: ${h.error.slice(0, 60)}`
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
