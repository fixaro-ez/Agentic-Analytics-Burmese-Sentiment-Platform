"use client"

import { FormEvent, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  CalendarClock,
  ChevronRight,
  CircleStop,
  ExternalLink,
  Play,
  Pause,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react"
import { useApi } from "@/hooks/use-api"
import { api } from "@/lib/api"
import { myanmarLangProps } from "@/lib/myanmar"
import { detectScrapeUrl, splitSseBuffer } from "@/lib/scrape-helpers"
import type {
  CookieStatus,
  SavedScrapeEntity,
  ScrapeReadiness,
  ScrapeRunHistory,
  ScrapeRunResponse,
  ScrapeRunStatus,
  ScrapeSchedule,
} from "@/lib/types"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useToast } from "@/components/ui/toast"

type Source = "facebook" | "foodpanda"
type DrawerTab = "saved" | "new" | "history" | "schedules"

const TERMINAL = new Set(["completed", "partial", "failed", "cancelled"])
const CRON_PRESETS = [
  { label: "Every 6 hours", value: "0 */6 * * *" },
  { label: "Daily at midnight", value: "0 0 * * *" },
  { label: "Weekly on Monday", value: "0 0 * * 1" },
] as const

function formatDate(value: string | null | undefined) {
  if (!value) return "Never"
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? "Unavailable"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date)
}

function statusTone(status: string | null | undefined) {
  if (status === "failed" || status === "cancelled") {
    return "border-pipeline-error/50 bg-pipeline-error/10 text-pipeline-error"
  }
  if (status === "running" || status === "queued" || status === "cancelling") {
    return "border-pipeline-active/50 bg-pipeline-active/10 text-pipeline-active"
  }
  return "border-pipeline-idle/50 bg-pipeline-idle/10 text-muted-foreground"
}

function ProgressRail({ value }: { value: number }) {
  return (
    <div
      className="h-2 overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-label="Scrape progress"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
    >
      <div
        className="h-full rounded-full bg-pipeline-active transition-[width] motion-reduce:transition-none"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  )
}

export function ScrapeManagerDrawer({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { toast } = useToast()
  const [tab, setTab] = useState<DrawerTab>("saved")
  const [step, setStep] = useState(1)
  const [source, setSource] = useState<Source>("facebook")
  const [url, setUrl] = useState("")
  const [entityName, setEntityName] = useState("")
  const [maxPosts, setMaxPosts] = useState(10)
  const [headless, setHeadless] = useState(true)
  const [saveForFuture, setSaveForFuture] = useState(false)
  const [runFullPipeline, setRunFullPipeline] = useState(true)
  const [busy, setBusy] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [liveStatus, setLiveStatus] = useState<ScrapeRunStatus | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [scheduleEntityId, setScheduleEntityId] = useState("")
  const [cronExpression, setCronExpression] = useState("0 0 * * *")

  const saved = useApi<SavedScrapeEntity[]>("/api/scraping/entities", {
    skip: !open,
  })
  const history = useApi<ScrapeRunHistory[]>("/api/scraping/history?limit=30", {
    skip: !open,
    refetchInterval: open ? 5_000 : false,
  })
  const schedules = useApi<ScrapeSchedule[]>("/api/scraping/schedules", {
    skip: !open,
  })
  const readiness = useApi<ScrapeReadiness>(
    `/api/scraping/readiness?source=${source}`,
    { skip: !open || tab !== "new" }
  )
  const cookies = useApi<CookieStatus>("/api/scraping/cookies", {
    skip: !open || tab !== "new" || source !== "facebook",
  })
  const polledStatus = useApi<ScrapeRunStatus>(
    `/api/scraping/status/${activeRunId ?? "none"}`,
    {
      skip: !activeRunId,
      refetchInterval: (query) => {
        const status = query.state.data?.status
        return status && TERMINAL.has(status) ? false : 3_000
      },
    }
  )
  const activeStatus = liveStatus ?? polledStatus.data

  useEffect(() => {
    if (!activeRunId) return
    const controller = new AbortController()
    let buffer = ""

    async function connect() {
      try {
        const response = await api.openStream(`/api/scraping/events/${activeRunId}`)
        if (!response.body) throw new Error("Streaming is not supported by this browser.")
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const parsed = splitSseBuffer(buffer)
          buffer = parsed.remainder
          for (const data of parsed.data) {
            setLiveStatus(JSON.parse(data) as ScrapeRunStatus)
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setStreamError(
            error instanceof Error
              ? `${error.message} Falling back to polling.`
              : "Live updates unavailable. Falling back to polling."
          )
        }
      }
    }
    void connect()
    return () => controller.abort()
  }, [activeRunId])

  const savedByUrl = useMemo(
    () => new Map((saved.data ?? []).map((entity) => [entity.source_url, entity])),
    [saved.data]
  )

  function handleUrl(value: string) {
    setUrl(value)
    const detected = detectScrapeUrl(value)
    if (detected.source) setSource(detected.source)
    if (detected.name && !entityName.trim()) setEntityName(detected.name)
  }

  function resetWizard() {
    setStep(1)
    setUrl("")
    setEntityName("")
    setMaxPosts(10)
    setHeadless(true)
    setSaveForFuture(false)
    setRunFullPipeline(true)
  }

  async function submitScrape(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const result = await api.post<ScrapeRunResponse>("/api/scraping/run", {
        source,
        url,
        entity_name: entityName,
        max_posts: maxPosts,
        headless: headless,
        save_for_future: saveForFuture,
        run_full_pipeline: runFullPipeline,
      })
      setActiveRunId(result.run_id)
      setLiveStatus(null)
      setStreamError(null)
      setTab("history")
      history.refetch()
      saved.refetch()
      toast({
        title: "Scrape queued",
        description: result.message,
        variant: "success",
      })
      resetWizard()
    } catch (error) {
      toast({
        title: "Could not start scrape",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    } finally {
      setBusy(false)
    }
  }

  async function runSaved(entity: SavedScrapeEntity) {
    setBusy(true)
    try {
      const result = await api.post<ScrapeRunResponse>(
        `/api/scraping/entities/${entity.id}/run`
      )
      setActiveRunId(result.run_id)
      setLiveStatus(null)
      setTab("history")
      toast({ title: "Re-scrape queued", variant: "success" })
    } catch (error) {
      toast({
        title: "Could not queue re-scrape",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    } finally {
      setBusy(false)
    }
  }

  async function removeSaved(entity: SavedScrapeEntity) {
    if (!window.confirm(`Delete saved target “${entity.display_name}”?`)) return
    try {
      await api.delete(`/api/scraping/entities/${entity.id}`)
      saved.refetch()
      schedules.refetch()
    } catch (error) {
      toast({
        title: "Could not delete saved target",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    }
  }

  async function requestCancellation(runId: string) {
    try {
      await api.post(`/api/scraping/cancel/${runId}`)
      polledStatus.refetch()
      history.refetch()
      toast({ title: "Cancellation requested", variant: "default" })
    } catch (error) {
      toast({
        title: "Could not request cancellation",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    }
  }

  async function cancelActive() {
    if (activeRunId) await requestCancellation(activeRunId)
  }

  async function saveSchedule(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      await api.post("/api/scraping/schedules", {
        entity_id: scheduleEntityId,
        cron_expression: cronExpression,
        timezone: "Asia/Yangon",
        active: true,
      })
      schedules.refetch()
      toast({ title: "Schedule saved", variant: "success" })
    } catch (error) {
      toast({
        title: "Could not save schedule",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    } finally {
      setBusy(false)
    }
  }

  async function removeSchedule(schedule: ScrapeSchedule) {
    if (!window.confirm(`Delete the schedule for “${schedule.display_name}”?`)) return
    try {
      await api.delete(`/api/scraping/schedules/${schedule.id}`)
      schedules.refetch()
    } catch (error) {
      toast({
        title: "Could not delete schedule",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    }
  }

  async function toggleSchedule(schedule: ScrapeSchedule) {
    try {
      await api.post("/api/scraping/schedules", {
        entity_id: schedule.entity_id,
        cron_expression: schedule.cron_expression,
        timezone: schedule.timezone,
        active: !schedule.active,
      })
      schedules.refetch()
    } catch (error) {
      toast({
        title: "Could not update schedule",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    }
  }

  async function uploadCookies(file: File | undefined) {
    if (!file) return
    const form = new FormData()
    form.append("file", file)
    try {
      await api.upload("/api/scraping/cookies", form)
      cookies.refetch()
      readiness.refetch()
      toast({ title: "Facebook cookies updated", variant: "success" })
    } catch (error) {
      toast({
        title: "Cookie upload failed",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-4xl overflow-y-auto overscroll-contain">
        <SheetHeader>
          <SheetTitle>Scrape Manager</SheetTitle>
          <SheetDescription>
            Save sources, run browser collection, inspect diagnostics, and schedule repeats.
          </SheetDescription>
        </SheetHeader>

        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as DrawerTab)}
          className="px-4 pb-8 pt-4 sm:px-6"
        >
          <TabsList className="grid h-auto w-full grid-cols-2 gap-1 sm:grid-cols-4">
            <TabsTrigger value="saved">Saved</TabsTrigger>
            <TabsTrigger value="new">New scrape</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
            <TabsTrigger value="schedules">Schedules</TabsTrigger>
          </TabsList>

          <TabsContent value="saved">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">Saved entities</h3>
                <p className="text-sm text-muted-foreground">
                  One-click collection with stored source options.
                </p>
              </div>
              <Button size="sm" onClick={() => setTab("new")} className="gap-2">
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add
              </Button>
            </div>
            {saved.loading && <p className="text-sm text-muted-foreground">Loading saved targets…</p>}
            {saved.error && (
              <p className="rounded-lg border border-pipeline-error/40 p-3 text-sm text-pipeline-error">
                {saved.error}
              </p>
            )}
            {!saved.loading && !saved.error && (saved.data?.length ?? 0) === 0 && (
              <div className="rounded-xl border border-dashed p-8 text-center">
                <Save className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden="true" />
                <p className="mt-3 font-medium">No saved sources yet</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Create a new scrape and enable “Save for future”.
                </p>
              </div>
            )}
            <div className="grid gap-3 md:grid-cols-2">
              {saved.data?.map((entity) => (
                <article key={entity.id} className="rounded-xl border p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h4 className="truncate font-medium" {...myanmarLangProps(entity.display_name)}>
                        {entity.display_name}
                      </h4>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {entity.source_url}
                      </p>
                    </div>
                    <Badge variant="outline" className="capitalize">{entity.source}</Badge>
                  </div>
                  <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <dt className="text-muted-foreground">Last scraped</dt>
                      <dd className="mt-0.5">{formatDate(entity.last_scraped_at)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Pipeline</dt>
                      <dd className="mt-0.5">{entity.auto_pipeline ? "Full pipeline" : "Scrape only"}</dd>
                    </div>
                  </dl>
                  {entity.last_scrape_status && (
                    <Badge
                      variant="outline"
                      className={cn("mt-3 capitalize", statusTone(entity.last_scrape_status))}
                    >
                      {entity.last_scrape_status}
                    </Badge>
                  )}
                  <div className="mt-4 flex gap-2">
                    <Button
                      size="sm"
                      className="flex-1 gap-2"
                      onClick={() => void runSaved(entity)}
                      disabled={busy}
                    >
                      <RefreshCw className="h-4 w-4" aria-hidden="true" />
                      Re-scrape
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => void removeSaved(entity)}
                      aria-label={`Delete ${entity.display_name}`}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="new">
            <ol className="mb-6 grid grid-cols-3 gap-2" aria-label="Scrape wizard progress">
              {["Source", "Options", "Review"].map((label, index) => {
                const number = index + 1
                return (
                  <li
                    key={label}
                    className={cn(
                      "rounded-lg border p-3 text-xs",
                      step === number && "border-pipeline-active bg-pipeline-active/5"
                    )}
                    aria-current={step === number ? "step" : undefined}
                  >
                    <span className="block text-muted-foreground">Step {number}</span>
                    <span className="mt-1 block font-medium">{label}</span>
                  </li>
                )
              })}
            </ol>

            <form onSubmit={submitScrape}>
              {step === 1 && (
                <div className="space-y-5">
                  <fieldset>
                    <legend className="text-sm font-medium">Source</legend>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {(["facebook", "foodpanda"] as const).map((value) => (
                        <Button
                          key={value}
                          type="button"
                          variant={source === value ? "default" : "outline"}
                          onClick={() => setSource(value)}
                          className="capitalize"
                        >
                          {value}
                        </Button>
                      ))}
                    </div>
                  </fieldset>
                  <div className="space-y-2">
                    <Label htmlFor="scrape-url">Page or shop URL</Label>
                    <Input
                      id="scrape-url"
                      type="url"
                      inputMode="url"
                      autoComplete="url"
                      value={url}
                      onChange={(event) => handleUrl(event.target.value)}
                      placeholder="https://www.facebook.com/BrandPage"
                      required
                    />
                    <p className="text-xs text-muted-foreground">
                      The source and entity name are inferred from supported URLs.
                    </p>
                  </div>
                  <div aria-live="polite">
                    {readiness.data && (
                      <p
                        className={cn(
                          "rounded-lg border p-3 text-sm",
                          readiness.data.ready
                            ? "border-pipeline-active/40"
                            : "border-pipeline-error/40 text-pipeline-error"
                        )}
                      >
                        {readiness.data.message}
                      </p>
                    )}
                    {source === "facebook" && cookies.data && !cookies.data.valid && (
                      <div className="mt-3 rounded-lg border p-3">
                        <p className="text-sm">{cookies.data.message}</p>
                        <Label htmlFor="cookie-file" className="mt-3 inline-block">
                          Upload cookies.json
                        </Label>
                        <Input
                          id="cookie-file"
                          type="file"
                          accept=".json,application/json"
                          className="mt-2"
                          onChange={(event) => void uploadCookies(event.target.files?.[0])}
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-5">
                  <div className="space-y-2">
                    <Label htmlFor="entity-name">Entity name</Label>
                    <Input
                      id="entity-name"
                      value={entityName}
                      onChange={(event) => setEntityName(event.target.value)}
                      autoComplete="organization"
                      required
                    />
                    <p className="text-xs text-muted-foreground">
                      Confirm this matches the name used by your analytics entity.
                    </p>
                  </div>
                  {source === "facebook" && (
                    <div className="space-y-2">
                      <Label htmlFor="max-posts">Maximum posts</Label>
                      <Select
                        value={String(maxPosts)}
                        onValueChange={(value) => setMaxPosts(Number(value))}
                      >
                        <SelectTrigger id="max-posts">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[5, 10, 25, 50, 100].map((value) => (
                            <SelectItem key={value} value={String(value)}>
                              {value} posts
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  <label className="flex min-h-11 items-start gap-3 rounded-lg border p-3">
                    <input
                      type="checkbox"
                      checked={headless}
                      onChange={(event) => setHeadless(event.target.checked)}
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-medium">Run headless</span>
                      <span className="text-xs text-muted-foreground">Recommended for scheduled and background runs.</span>
                    </span>
                  </label>
                  {runFullPipeline && readiness.data?.pipeline_ready === false && (
                    <p role="alert" className="text-sm text-pipeline-error">
                      {readiness.data.pipeline_message ??
                        "The cleaning, NLP, or PostgreSQL stage is unavailable."}
                    </p>
                  )}
                  <label className="flex min-h-11 items-start gap-3 rounded-lg border p-3">
                    <input
                      type="checkbox"
                      checked={saveForFuture}
                      onChange={(event) => setSaveForFuture(event.target.checked)}
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-medium">Save for future</span>
                      <span className="text-xs text-muted-foreground">Adds this source to Saved entities.</span>
                    </span>
                  </label>
                  <label className="flex min-h-11 items-start gap-3 rounded-lg border p-3">
                    <input
                      type="checkbox"
                      checked={runFullPipeline}
                      onChange={(event) => setRunFullPipeline(event.target.checked)}
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-medium">Run full pipeline</span>
                      <span className="text-xs text-muted-foreground">
                        Clean → NLP → validated Postgres load after collection. On by default.
                      </span>
                    </span>
                  </label>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-4">
                  <div className="rounded-xl border bg-muted/20 p-4">
                    <h3 className="font-medium" {...myanmarLangProps(entityName)}>
                      {entityName}
                    </h3>
                    <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                      <div><dt className="text-muted-foreground">Source</dt><dd className="capitalize">{source}</dd></div>
                      <div><dt className="text-muted-foreground">Limit</dt><dd>{source === "facebook" ? `${maxPosts} posts` : "All available reviews"}</dd></div>
                      <div><dt className="text-muted-foreground">Saved</dt><dd>{saveForFuture ? "Yes" : "No"}</dd></div>
                      <div><dt className="text-muted-foreground">Pipeline</dt><dd>{runFullPipeline ? "Full pipeline" : "Scrape only"}</dd></div>
                    </dl>
                    <p className="mt-4 break-all text-xs text-muted-foreground">{url}</p>
                  </div>
                </div>
              )}

              <div className="mt-6 flex items-center justify-between gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setStep((value) => Math.max(1, value - 1))}
                  disabled={step === 1 || busy}
                >
                  Back
                </Button>
                {step < 3 ? (
                  <Button
                    type="button"
                    onClick={(event) => {
                      // Prevent native form submission if React reuses this DOM
                      // node while replacing it with the step-3 submit button.
                      event.preventDefault()
                      setStep((value) => Math.min(3, value + 1))
                    }}
                    disabled={
                      (step === 1 && (!url || !detectScrapeUrl(url).source)) ||
                      (step === 2 && !entityName.trim()) ||
                      readiness.data?.ready === false
                    }
                    className="gap-2"
                  >
                    Continue
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    disabled={
                      busy ||
                      (runFullPipeline &&
                        readiness.data?.pipeline_ready === false)
                    }
                    className="gap-2"
                  >
                    <Play className="h-4 w-4" aria-hidden="true" />
                    {busy ? "Queueing…" : "Start scrape"}
                  </Button>
                )}
              </div>
            </form>
          </TabsContent>

          <TabsContent value="history">
            {activeStatus && (
              <section className="mb-5 rounded-xl border border-pipeline-active/40 bg-pipeline-active/5 p-4" aria-live="polite">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-medium" {...myanmarLangProps(activeStatus.entity_name)}>
                      {activeStatus.entity_name || "Active scrape"}
                    </h3>
                    <p className="mt-1 text-sm capitalize text-muted-foreground">
                      {(activeStatus.phase ?? activeStatus.status).replaceAll("_", " ")}
                    </p>
                  </div>
                  <Badge variant="outline" className={cn("capitalize", statusTone(activeStatus.status))}>
                    {activeStatus.status}
                  </Badge>
                </div>
                <div className="mt-4">
                  <ProgressRail value={activeStatus.progress_percent ?? 0} />
                </div>
                {streamError && <p className="mt-2 text-xs text-muted-foreground">{streamError}</p>}
                {!TERMINAL.has(activeStatus.status) && (
                  <Button variant="outline" size="sm" className="mt-4 gap-2" onClick={() => void cancelActive()}>
                    <CircleStop className="h-4 w-4" aria-hidden="true" />
                    Cancel
                  </Button>
                )}
                {activeStatus.error && <p className="mt-3 text-sm text-pipeline-error">{activeStatus.error}</p>}
              </section>
            )}
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="font-medium">Run history</h3>
                <p className="text-sm text-muted-foreground">Expand a run for diagnostics and source metadata.</p>
              </div>
              <Button variant="ghost" size="icon" onClick={history.refetch} aria-label="Refresh scrape history">
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            {history.loading && <p className="text-sm text-muted-foreground">Loading history…</p>}
            {history.error && <p className="text-sm text-pipeline-error">{history.error}</p>}
            <div className="space-y-2">
              {history.data?.map((run) => {
                const stats = run.stats ?? {}
                const runUrl = String(stats.url ?? "")
                const matched = savedByUrl.get(runUrl)
                const dashboardHref = matched?.dim_entity_id
                  ? `/dashboard?entity=${matched.dim_entity_id}&days=30`
                  : "/dashboard?days=30"
                return (
                  <details key={run.run_id} className="group rounded-xl border p-4">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium" {...myanmarLangProps(String(stats.entity_name ?? ""))}>
                          {String(stats.entity_name ?? run.run_type.replace("scrape_", ""))}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">{formatDate(run.started_at)}</p>
                      </div>
                      <Badge variant="outline" className={cn("capitalize", statusTone(run.status))}>
                        {run.status}
                      </Badge>
                    </summary>
                    <div className="mt-4 border-t pt-4 text-sm">
                      {run.error && <p className="rounded-md bg-pipeline-error/10 p-3 text-pipeline-error">{run.error}</p>}
                      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                        {Object.entries(stats).map(([key, value]) => (
                          <div key={key} className="min-w-0">
                            <dt className="text-xs capitalize text-muted-foreground">{key.replaceAll("_", " ")}</dt>
                            <dd className="truncate text-xs">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                      <Button asChild variant="outline" size="sm" className="mt-4 gap-2">
                        <Link href={dashboardHref}>
                          Dashboard
                          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                        </Link>
                      </Button>
                      {!TERMINAL.has(run.status) && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setActiveRunId(run.run_id)
                              setLiveStatus(null)
                              setStreamError(null)
                            }}
                          >
                            Track live
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={() => void requestCancellation(run.run_id)}
                          >
                            <CircleStop className="h-4 w-4" aria-hidden="true" />
                            Cancel run
                          </Button>
                        </div>
                      )}
                    </div>
                  </details>
                )
              })}
            </div>
          </TabsContent>

          <TabsContent value="schedules">
            <div className="mb-5">
              <h3 className="font-medium">Scrape schedules</h3>
              <p className="text-sm text-muted-foreground">
                Schedules run in Asia/Yangon while the local backend is online.
              </p>
            </div>
            <form onSubmit={saveSchedule} className="rounded-xl border p-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="schedule-entity">Saved entity</Label>
                  <Select value={scheduleEntityId} onValueChange={setScheduleEntityId}>
                    <SelectTrigger id="schedule-entity">
                      <SelectValue placeholder="Select a saved target" />
                    </SelectTrigger>
                    <SelectContent>
                      {saved.data?.map((entity) => (
                        <SelectItem key={entity.id} value={entity.id}>
                          {entity.display_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="schedule-preset">Frequency</Label>
                  <Select value={cronExpression} onValueChange={setCronExpression}>
                    <SelectTrigger id="schedule-preset"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CRON_PRESETS.map((preset) => (
                        <SelectItem key={preset.value} value={preset.value}>{preset.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="mt-4 space-y-2">
                <Label htmlFor="cron-expression">Cron expression</Label>
                <Input
                  id="cron-expression"
                  value={cronExpression}
                  onChange={(event) => setCronExpression(event.target.value)}
                  spellCheck={false}
                  placeholder="0 0 * * *"
                />
                <p className="text-xs text-muted-foreground">Five-field cron: minute hour day month weekday.</p>
              </div>
              <Button type="submit" className="mt-4 gap-2" disabled={!scheduleEntityId || busy}>
                <CalendarClock className="h-4 w-4" aria-hidden="true" />
                Save schedule
              </Button>
            </form>

            <div className="mt-5 space-y-2">
              {schedules.loading && <p className="text-sm text-muted-foreground">Loading schedules…</p>}
              {schedules.error && <p className="text-sm text-pipeline-error">{schedules.error}</p>}
              {!schedules.loading && (schedules.data?.length ?? 0) === 0 && (
                <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
                  No schedules yet.
                </p>
              )}
              {schedules.data?.map((schedule) => (
                <div key={schedule.id} className="flex items-center justify-between gap-3 rounded-xl border p-4">
                  <div className="min-w-0">
                    <p className="truncate font-medium" {...myanmarLangProps(schedule.display_name)}>
                      {schedule.display_name}
                    </p>
                    <p className="mt-1 font-mono text-xs text-muted-foreground">{schedule.cron_expression}</p>
                    <p className="mt-1 text-xs text-muted-foreground">Next: {formatDate(schedule.next_run)}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => void toggleSchedule(schedule)}
                      aria-label={`${schedule.active ? "Pause" : "Resume"} schedule for ${schedule.display_name}`}
                    >
                      {schedule.active ? (
                        <Pause className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <Play className="h-4 w-4" aria-hidden="true" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => void removeSchedule(schedule)}
                      aria-label={`Delete schedule for ${schedule.display_name}`}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
