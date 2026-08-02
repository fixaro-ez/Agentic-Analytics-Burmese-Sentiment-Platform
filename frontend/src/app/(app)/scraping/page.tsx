"use client"

import { useState, useEffect, useMemo } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { myanmarLangProps } from "@/lib/myanmar"
import { useApi } from "@/hooks/use-api"
import type {
  ScrapeRunResponse,
  ScrapeRunStatus,
  ScrapeRunHistory,
  CookieStatus,
  ScrapeReadiness,
  EntityListResponse,
} from "@/lib/types"

const HISTORY_PAGE_SIZE = 5

function validateScrapeUrl(
  source: "facebook" | "foodpanda",
  rawUrl: string
): string | null {
  if (!rawUrl.trim()) return null
  let parsed: URL
  try {
    parsed = new URL(rawUrl.trim())
  } catch {
    return "Enter a complete URL beginning with http:// or https://."
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    return "Enter a complete URL beginning with http:// or https://."
  }
  const hostname = parsed.hostname.toLowerCase()
  if (source === "facebook") {
    if (!(hostname === "facebook.com" || hostname.endsWith(".facebook.com"))) {
      return "Facebook scraping requires a facebook.com URL."
    }
    let decodedPath: string
    try {
      decodedPath = decodeURIComponent(parsed.pathname)
    } catch {
      return "The Facebook URL contains invalid encoding."
    }
    if (/\s/.test(decodedPath)) {
      return (
        "Facebook page URLs cannot contain spaces. Copy the exact page address, " +
        "for example https://www.facebook.com/LotteriaMyanmar."
      )
    }
    if (!decodedPath.replaceAll("/", "") && !parsed.search) {
      return "Enter a specific Facebook page or post URL."
    }
  } else if (!hostname.includes("foodpanda.")) {
    return "Foodpanda scraping requires a Foodpanda URL."
  }
  return null
}

function scrapeHistorySummary(run: ScrapeRunHistory): string {
  if (run.status === "failed" && run.error) return `Error: ${run.error}`
  const stats = run.stats
  if (!stats) return "No diagnostics"
  const parts: string[] = []
  if (typeof stats.posts_scraped === "number") {
    parts.push(
      `${stats.posts_scraped}/${typeof stats.posts_requested === "number" ? stats.posts_requested : stats.posts_scraped} posts`
    )
  } else if (typeof stats.reviews_scraped === "number") {
    parts.push(`${stats.reviews_scraped} reviews`)
  }
  if (
    typeof stats.mongo_inserted === "number" ||
    typeof stats.mongo_updated === "number"
  ) {
    parts.push(
      `Mongo: ${Number(stats.mongo_inserted ?? 0)} new, ${Number(stats.mongo_updated ?? 0)} updated`
    )
  }
  if (stats.etl_status === "completed") {
    parts.push("Cleaned, analyzed, and published")
  } else if (stats.etl_status === "not_requested") {
    parts.push("Collection only")
  }
  return parts.join(" · ") || "Diagnostics available"
}

export default function ScrapingPage() {
  // ---- Form state ----
  const [source, setSource] = useState<"facebook" | "foodpanda">("facebook")
  const [url, setUrl] = useState("")
  const [entityName, setEntityName] = useState("")
  const [maxPosts, setMaxPosts] = useState(10)
  const [headless, setHeadless] = useState(true)
  const [runFullPipeline, setRunFullPipeline] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ---- Cookie status (Facebook) ----
  const [cookies, setCookies] = useState<CookieStatus | null>(null)
  const [readiness, setReadiness] = useState<ScrapeReadiness | null>(null)
  const [checkingReadiness, setCheckingReadiness] = useState(true)

  // ---- Cookie upload ----
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  // ---- Running job polling ----
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [historyPage, setHistoryPage] = useState(0)

  // ---- History ----
  const {
    data: history = [],
    loading: loadingHistory,
    refetch: fetchHistory,
  } = useApi<ScrapeRunHistory[]>("/api/scraping/history?limit=20")
  const historyPageCount = Math.max(
    1,
    Math.ceil(history.length / HISTORY_PAGE_SIZE)
  )
  const visibleHistory = history.slice(
    historyPage * HISTORY_PAGE_SIZE,
    (historyPage + 1) * HISTORY_PAGE_SIZE
  )

  // ---- Entity name suggestions ----
  const { data: entitiesData } = useApi<EntityListResponse>("/api/entities")
  const entitySuggestions = useMemo(() => {
    const all = entitiesData?.entities ?? []
    return all
      .filter((e) => e.platform.toLowerCase() === source)
      .map((e) => e.entity_name)
      .filter((name, i, arr) => arr.indexOf(name) === i)
  }, [entitiesData, source])
  const successfulEntityUrls = useMemo(() => {
    const urls = new Map<string, string>()
    for (const run of history) {
      if (!["completed", "partial"].includes(run.status) || !run.stats) continue
      const runSource = run.run_type.replace("scrape_", "")
      const runEntity = run.stats.entity_name
      const runUrl = run.stats.url
      if (
        runSource !== source ||
        typeof runEntity !== "string" ||
        typeof runUrl !== "string"
      ) {
        continue
      }
      const key = runEntity.trim().toLowerCase()
      if (!urls.has(key)) urls.set(key, runUrl)
    }
    return urls
  }, [history, source])
  const urlValidationError = useMemo(
    () => validateScrapeUrl(source, url),
    [source, url]
  )

  // Fetch cookie status on mount (and when source changes to facebook)
  useEffect(() => {
    if (source === "facebook") {
      api.get<CookieStatus>("/api/scraping/cookies").then(setCookies).catch(() => {})
    }
  }, [source])

  async function fetchReadiness(selectedSource = source) {
    setCheckingReadiness(true)
    try {
      const status = await api.get<ScrapeReadiness>(
        `/api/scraping/readiness?source=${selectedSource}`
      )
      setReadiness(status)
      return status
    } catch (err) {
      const message = err instanceof Error ? err.message : "Preflight check failed"
      setReadiness({
        source: selectedSource,
        ready: false,
        mongodb_ready: false,
        cookies_ready: selectedSource === "facebook" ? false : null,
        message,
      })
      return null
    } finally {
      setCheckingReadiness(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    api
      .get<ScrapeReadiness>(`/api/scraping/readiness?source=${source}`)
      .then((status) => {
        if (!cancelled) setReadiness(status)
      })
      .catch((err) => {
        if (cancelled) return
        setReadiness({
          source,
          ready: false,
          mongodb_ready: false,
          cookies_ready: source === "facebook" ? false : null,
          message: err instanceof Error ? err.message : "Preflight check failed",
        })
      })
      .finally(() => {
        if (!cancelled) setCheckingReadiness(false)
      })
    return () => {
      cancelled = true
    }
  }, [source])

  // Poll active run status every 3 seconds via TanStack Query; polling stops
  // automatically at a terminal status or on error.
  const { data: activeStatus, error: activeStatusError } =
    useApi<ScrapeRunStatus>(
      activeRunId ? `/api/scraping/status/${activeRunId}` : "",
      {
        skip: !activeRunId,
        refetchInterval: (query) => {
          if (query.state.status === "error") return false
          const status = query.state.data?.status
          if (
            status &&
            ["completed", "partial", "failed", "cancelled"].includes(status)
          ) {
            return false
          }
          return 3000
        },
      }
    )

  // Derived (no setState-in-effect): the run is only "active" while it has no
  // terminal status and the poll hasn't died without data. Once finished, the
  // panel hides and the start button re-enables — same as the old manual loop.
  const finished =
    activeStatus != null &&
    ["completed", "partial", "failed", "cancelled"].includes(activeStatus.status)
  const pollDead = activeStatusError != null && activeStatus == null
  const runActive = activeRunId != null && !finished && !pollDead

  // Refresh the history table once when a run completes.
  useEffect(() => {
    if (finished) fetchHistory()
  }, [finished, fetchHistory])

  // ---- Cookie upload handler ----
  async function handleUploadCookies(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    setUploading(true)
    setUploadError(null)

    const formData = new FormData()
    formData.append("file", file)

    try {
      const status = await api.upload<CookieStatus>(
        "/api/scraping/cookies",
        formData
      )
      setCookies(status)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setUploading(false)
      if (event.target) event.target.value = ""
    }
  }

  // ---- Submit handler ----
  async function handleStartScrape() {
    if (!url.trim() || !entityName.trim()) {
      setError("URL and Entity name are required.")
      return
    }
    if (urlValidationError) {
      setError(urlValidationError)
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const currentReadiness = await fetchReadiness()
      if (!currentReadiness?.ready) {
        setError(
          currentReadiness?.message ??
            "Scraper prerequisites are unavailable. Check MongoDB and cookies."
        )
        return
      }
      const res = await api.post<ScrapeRunResponse>("/api/scraping/run", {
        source,
        url: url.trim(),
        entity_name: entityName.trim(),
        max_posts: maxPosts,
        headless,
        run_full_pipeline: runFullPipeline,
      })
      setActiveRunId(res.run_id)
      setHistoryPage(0)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start scrape")
    } finally {
      setSubmitting(false)
    }
  }

  function statusBadge(status: string) {
    if (status === "completed")
      return (
        <Badge className="bg-pipeline-active text-primary-foreground">
          Completed
        </Badge>
      )
    if (status === "partial")
      return <Badge className="bg-pipeline-idle text-white">Partial</Badge>
    if (status === "failed")
      return (
        <Badge className="bg-pipeline-error text-destructive-foreground">
          Failed
        </Badge>
      )
    if (status === "cancelled")
      return <Badge variant="secondary">Cancelled</Badge>
    return (
      <Badge className="bg-pipeline-active text-primary-foreground">
        Running
      </Badge>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Scraping</h1>

      {/* ---- Scrape Form ---- */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle>New scrape</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 border-b pb-4">
            <Label>Source</Label>
            <div className="flex gap-2">
              {(["facebook", "foodpanda"] as const).map((s) => (
                <Button
                  key={s}
                  type="button"
                  variant={source === s ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setSource(s)
                    setReadiness(null)
                    setCheckingReadiness(true)
                  }}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </Button>
              ))}
            </div>
            <div
              className="ml-auto flex flex-wrap items-center gap-2 text-sm"
              role="status"
              aria-live="polite"
            >
              <span className="text-muted-foreground">Database</span>
              <Badge
                className={
                  readiness?.mongodb_ready
                    ? "bg-pipeline-active text-primary-foreground"
                    : "bg-pipeline-error text-destructive-foreground"
                }
              >
                {checkingReadiness
                  ? "Checking"
                  : readiness?.mongodb_ready
                    ? "Ready"
                    : "Unavailable"}
              </Badge>
              <span className="ml-2 text-muted-foreground">Processing</span>
              <Badge
                className={
                  readiness?.pipeline_ready
                    ? "bg-pipeline-active text-primary-foreground"
                    : "bg-pipeline-error text-destructive-foreground"
                }
              >
                {checkingReadiness
                  ? "Checking"
                  : readiness?.pipeline_ready
                    ? "Ready"
                    : "Unavailable"}
              </Badge>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void fetchReadiness()}
                disabled={checkingReadiness}
              >
                Refresh
              </Button>
            </div>
          </div>

          {source === "facebook" && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Cookies</span>
              {cookies ? (
                cookies.valid ? (
                  <Badge className="bg-pipeline-active text-primary-foreground">
                    {cookies.expires_at
                      ? `Valid until ${cookies.expires_at.slice(0, 10)}`
                      : "Valid"}
                  </Badge>
                ) : (
                  <Badge className="bg-pipeline-error text-destructive-foreground">
                    {cookies.message}
                  </Badge>
                )
              ) : (
                <Badge variant="secondary">Checking</Badge>
              )}
              <input
                type="file"
                id="cookie-upload"
                accept=".json"
                onChange={handleUploadCookies}
                className="hidden"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => document.getElementById("cookie-upload")?.click()}
                disabled={uploading}
              >
                {uploading ? "Uploading..." : cookies?.valid ? "Replace" : "Upload"}
              </Button>
              {uploadError && <p className="text-destructive">{uploadError}</p>}
            </div>
          )}

          {readiness && !readiness.ready && (
            <p className="text-sm text-destructive">{readiness.message}</p>
          )}
          {readiness?.pipeline_ready === false && readiness.pipeline_message && (
            <p className="text-sm text-destructive">{readiness.pipeline_message}</p>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="scrape-url">URL</Label>
              <Input
                id="scrape-url"
                placeholder={
                  source === "facebook"
                    ? "https://www.facebook.com/YourPage"
                    : "https://www.foodpanda.com.mm/restaurant/..."
                }
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                aria-invalid={urlValidationError ? true : undefined}
                aria-describedby={urlValidationError ? "scrape-url-error" : undefined}
              />
              {urlValidationError && (
                <p id="scrape-url-error" role="alert" className="text-sm text-destructive">
                  {urlValidationError}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="scrape-entity">Entity name</Label>
              <Input
                id="scrape-entity"
                list="entity-suggestions"
                placeholder="e.g. KFC Myanmar"
                value={entityName}
                {...myanmarLangProps(entityName)}
                onChange={(e) => {
                  const nextEntityName = e.target.value
                  setEntityName(nextEntityName)
                  const knownUrl = successfulEntityUrls.get(
                    nextEntityName.trim().toLowerCase()
                  )
                  if (knownUrl) setUrl(knownUrl)
                }}
              />
              {entitySuggestions.length > 0 && (
                <datalist id="entity-suggestions">
                  {entitySuggestions.map((name) => (
                    <option
                      key={name}
                      value={name}
                      {...myanmarLangProps(name)}
                    />
                  ))}
                </datalist>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
            {source === "facebook" && (
              <div className="space-y-2">
                <Label htmlFor="scrape-max">Post limit</Label>
                <Input
                  id="scrape-max"
                  type="number"
                  min={1}
                  max={200}
                  value={maxPosts}
                  onChange={(e) => setMaxPosts(parseInt(e.target.value) || 10)}
                  className="w-28"
                />
              </div>
            )}

            <div className="flex min-h-10 items-center gap-2">
              <input
                type="checkbox"
                id="scrape-headless"
                checked={headless}
                onChange={(e) => setHeadless(e.target.checked)}
                className="h-4 w-4"
              />
              <Label htmlFor="scrape-headless" className="cursor-pointer">
                Hide browser window
              </Label>
            </div>

            <div className="flex min-h-10 items-center gap-2">
              <input
                type="checkbox"
                id="scrape-full-pipeline"
                checked={runFullPipeline}
                onChange={(e) => setRunFullPipeline(e.target.checked)}
                className="h-4 w-4"
              />
              <Label htmlFor="scrape-full-pipeline" className="cursor-pointer">
                Publish to dashboard
              </Label>
            </div>
          </div>

          {/* Error */}
          {error && <p className="text-sm text-destructive">{error}</p>}

          {/* Submit */}
          <Button
            onClick={handleStartScrape}
            disabled={
              submitting ||
              checkingReadiness ||
              runActive ||
              !!urlValidationError ||
              readiness?.ready === false ||
              (runFullPipeline && readiness?.pipeline_ready === false)
            }
          >
            {submitting ? "Starting..." : runActive ? "Running..." : "Start scrape"}
          </Button>
        </CardContent>
      </Card>

      {/* ---- Active Job Status ---- */}
      {activeRunId && (
        <Card>
          <CardHeader className="pb-4">
            <CardTitle>{runActive ? "Running scrape" : "Latest scrape"}</CardTitle>
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
                  <span className="font-medium">Entity:</span>{" "}
                  <span {...myanmarLangProps(activeStatus.entity_name)}>
                    {activeStatus.entity_name}
                  </span>
                </p>
                <div className="flex items-center gap-1">
                  <span className="font-medium">Status:</span>{" "}
                  {statusBadge(activeStatus.status)}
                </div>
                {activeStatus.phase && (
                  <p>
                    <span className="font-medium">Pipeline stage:</span>{" "}
                    {activeStatus.phase.replaceAll("_", " ")}
                    {typeof activeStatus.progress_percent === "number"
                      ? ` (${activeStatus.progress_percent}%)`
                      : ""}
                  </p>
                )}
                {typeof activeStatus.stats?.posts_scraped === "number" && (
                  <p>
                    <span className="font-medium">Posts:</span>{" "}
                    {activeStatus.stats.posts_scraped}/
                    {typeof activeStatus.stats.posts_requested === "number"
                      ? activeStatus.stats.posts_requested
                      : activeStatus.stats.posts_scraped}{" "}
                    saved
                    {typeof activeStatus.stats.mongo_inserted === "number" &&
                      typeof activeStatus.stats.mongo_updated === "number" &&
                      ` (${activeStatus.stats.mongo_inserted} inserted, ${activeStatus.stats.mongo_updated} updated)`}
                  </p>
                )}
                {activeStatus.etl_run_id &&
                  ["completed", "partial"].includes(activeStatus.status) && (
                  <p className="text-muted-foreground">
                    Data processing and dashboard export completed.
                  </p>
                )}
                {activeStatus.stats?.etl_status === "not_requested" && (
                  <p className="text-amber-700">
                    Collection completed without cleaning, NLP, or PostgreSQL export.
                  </p>
                )}
                {typeof activeStatus.stats?.warning === "string" && (
                  <p className="text-amber-700">{activeStatus.stats.warning}</p>
                )}
                {activeStatus.error && (
                  <p className="text-destructive">{activeStatus.error}</p>
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
        <CardHeader className="pb-4">
          <CardTitle>History</CardTitle>
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
            <div className="space-y-4">
              <div className="overflow-x-auto">
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
                    {visibleHistory.map((h) => (
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
                        <TableCell className="max-w-lg whitespace-normal break-words text-xs">
                          {scrapeHistorySummary(h)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {history.length > HISTORY_PAGE_SIZE && (
                <div className="flex items-center justify-between border-t pt-4">
                  <p className="text-sm text-muted-foreground">
                    {historyPage * HISTORY_PAGE_SIZE + 1}–
                    {Math.min(
                      (historyPage + 1) * HISTORY_PAGE_SIZE,
                      history.length
                    )}{" "}
                    of {history.length}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={historyPage === 0}
                      onClick={() => setHistoryPage((page) => page - 1)}
                    >
                      Previous
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={historyPage >= historyPageCount - 1}
                      onClick={() => setHistoryPage((page) => page + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
