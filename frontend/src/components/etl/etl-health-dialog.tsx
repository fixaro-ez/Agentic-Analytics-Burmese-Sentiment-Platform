"use client"

import { useMemo, useState } from "react"
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Database,
  RefreshCw,
  Server,
} from "lucide-react"
import { useEtlHealth } from "@/hooks/use-analytics"
import type { PipelineNodeHealth, PipelineStatus } from "@/lib/types"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const NODE_ICONS = {
  scraper: Activity,
  mongodb: Database,
  nlp: BrainCircuit,
  postgresql: Server,
} as const

function statusClass(status: PipelineStatus) {
  if (status === "error" || status === "unavailable") {
    return "border-pipeline-error/50 bg-pipeline-error/10 text-pipeline-error"
  }
  if (status === "active" || status === "healthy") {
    return "border-pipeline-active/50 bg-pipeline-active/10 text-pipeline-active"
  }
  return "border-pipeline-idle/60 bg-pipeline-idle/10 text-muted-foreground"
}

function formatMetric(value: unknown) {
  if (value == null) return "—"
  if (typeof value === "number") return new Intl.NumberFormat().format(value)
  if (typeof value === "boolean") return value ? "Yes" : "No"
  return String(value).replaceAll("_", " ")
}

function formatDate(value: string | null) {
  if (!value) return "Never"
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? "Unavailable"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date)
}

function NodeCard({
  node,
  selected,
  onSelect,
}: {
  node: PipelineNodeHealth
  selected: boolean
  onSelect: () => void
}) {
  const Icon = NODE_ICONS[node.id]
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "min-w-0 rounded-xl border p-4 text-left outline-none transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring",
        selected && "border-pipeline-active bg-pipeline-active/5"
      )}
      aria-pressed={selected}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="rounded-lg border bg-background p-2">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <Badge variant="outline" className={cn("capitalize", statusClass(node.status))}>
          {node.status}
        </Badge>
      </div>
      <p className="mt-4 font-medium">{node.label}</p>
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
        {node.detail}
      </p>
    </button>
  )
}

export function EtlHealthDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const health = useEtlHealth(60_000, { skip: !open })
  const [selectedId, setSelectedId] = useState<PipelineNodeHealth["id"]>("scraper")
  const selected = useMemo(
    () => health.data?.nodes.find((node) => node.id === selectedId),
    [health.data, selectedId]
  )
  const nodes = health.data?.nodes ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-5xl overflow-y-auto overscroll-contain p-0">
        <DialogHeader className="border-b px-5 py-5 sm:px-6">
          <div className="flex flex-col gap-3 pr-8 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <DialogTitle>System &amp; ETL Health</DialogTitle>
              <DialogDescription className="mt-1">
                Read-only status from collection through the analytics warehouse.
              </DialogDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-fit gap-2"
              onClick={health.refetch}
              disabled={health.loading}
            >
              <RefreshCw
                className={cn(
                  "h-4 w-4",
                  health.loading && "motion-safe:animate-spin"
                )}
                aria-hidden="true"
              />
              Force refresh
            </Button>
          </div>
        </DialogHeader>

        <div className="space-y-6 px-5 py-5 sm:px-6">
          <div aria-live="polite" className="text-sm">
            {health.loading && !health.data && (
              <p className="text-muted-foreground">Checking every pipeline node…</p>
            )}
            {health.error && (
              <div className="rounded-lg border border-pipeline-error/40 bg-pipeline-error/10 p-3 text-pipeline-error">
                Health endpoint unavailable: {health.error}
              </div>
            )}
            {health.data && (
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant="outline"
                  className={cn("capitalize", statusClass(health.data.overall_status))}
                >
                  Overall {health.data.overall_status}
                </Badge>
                <span className="text-muted-foreground">
                  Checked {formatDate(health.data.generated_at)} · stale after{" "}
                  {health.data.stale_after_minutes} minutes
                </span>
              </div>
            )}
          </div>

          {health.data && (
            <>
              <section aria-labelledby="pipeline-flow-title">
                <h3 id="pipeline-flow-title" className="mb-3 text-sm font-medium">
                  Pipeline flow
                </h3>
                <div className="grid items-center gap-2 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]">
                  {nodes.map((node, index) => (
                    <div key={node.id} className="contents">
                      <NodeCard
                        node={node}
                        selected={selectedId === node.id}
                        onSelect={() => setSelectedId(node.id)}
                      />
                      {index < nodes.length - 1 && (
                        <ArrowRight
                          className="mx-auto hidden h-4 w-4 text-muted-foreground md:block"
                          aria-hidden="true"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </section>

              {selected && (
                <section
                  aria-labelledby="selected-node-title"
                  className="rounded-xl border bg-muted/20 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 id="selected-node-title" className="font-medium">
                      {selected.label} details
                    </h3>
                    <span className="text-xs text-muted-foreground">
                      Last activity {formatDate(selected.last_activity_at)}
                    </span>
                  </div>
                  <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {Object.entries(selected.metrics).map(([key, value]) => (
                      <div key={key} className="rounded-lg border bg-background p-3">
                        <dt className="text-xs capitalize text-muted-foreground">
                          {key.replaceAll("_", " ")}
                        </dt>
                        <dd className="mt-1 font-mono text-sm">{formatMetric(value)}</dd>
                      </div>
                    ))}
                  </dl>
                  {selected.error && (
                    <p className="mt-3 rounded-md bg-pipeline-error/10 p-3 text-sm text-pipeline-error">
                      {selected.error}
                    </p>
                  )}
                </section>
              )}

              <section aria-labelledby="load-status-title">
                <h3 id="load-status-title" className="mb-3 text-sm font-medium">
                  Postgres load status
                </h3>
                <div className="rounded-xl border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Table</TableHead>
                        <TableHead className="text-right">Rows</TableHead>
                        <TableHead className="text-right">Last load delta</TableHead>
                        <TableHead>Last loaded</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {health.data.loads.map((load) => (
                        <TableRow key={load.table}>
                          <TableCell className="font-mono text-xs">{load.table}</TableCell>
                          <TableCell className="text-right">
                            {formatMetric(load.row_count)}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatMetric(load.rows_loaded)}
                          </TableCell>
                          <TableCell>{formatDate(load.last_loaded_at)}</TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={cn("capitalize", statusClass(load.status))}
                            >
                              {load.status}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </section>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
