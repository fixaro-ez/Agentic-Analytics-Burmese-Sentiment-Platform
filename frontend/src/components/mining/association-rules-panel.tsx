"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  ExternalLink,
  Grid3X3,
  Network,
  SlidersHorizontal,
} from "lucide-react"

import { DataError } from "@/components/data-error"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/use-api"
import { buildForceGraph } from "@/lib/mining-visuals"
import { myanmarLangProps } from "@/lib/myanmar"
import type {
  AssociationRule,
  AssociationRuleResponse,
} from "@/lib/types"
import { ASPECT_LABELS } from "@/lib/types"
import { cn } from "@/lib/utils"

interface AssociationRulesPanelProps {
  entityId: number | null
  compareIds: number[]
  days: number
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function ruleKey(rule: AssociationRule) {
  return `${rule.antecedent.join("+")}→${rule.consequent.join("+")}`
}

function aspectLabel(value: string) {
  return ASPECT_LABELS[value] ?? value.replaceAll("_", " ")
}

function AssociationNetwork({
  rules,
  selectedKey,
  onSelect,
}: {
  rules: AssociationRule[]
  selectedKey: string | null
  onSelect: (rule: AssociationRule) => void
}) {
  const layout = useMemo(() => buildForceGraph(rules), [rules])

  return (
    <div className="overflow-hidden rounded-xl border bg-background">
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="block min-h-[22rem] w-full"
        role="img"
        aria-label={`Topic connection map with ${layout.nodes.length} topics and ${layout.edges.length} patterns`}
      >
        <defs>
          <marker
            id="rule-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent-primary)" />
          </marker>
        </defs>
        <g>
          {layout.edges.map((edge) => {
            const key = ruleKey(edge.rule)
            const selected = key === selectedKey
            const dx = edge.target.x - edge.source.x
            const dy = edge.target.y - edge.source.y
            const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
            const sourceRadius = 28 + Math.min(edge.source.degree, 8) * 1.4
            const targetRadius = 31 + Math.min(edge.target.degree, 8) * 1.4
            const x1 = edge.source.x + (dx / distance) * sourceRadius
            const y1 = edge.source.y + (dy / distance) * sourceRadius
            const x2 = edge.target.x - (dx / distance) * targetRadius
            const y2 = edge.target.y - (dy / distance) * targetRadius
            return (
              <g key={`${key}-${edge.ruleIndex}`}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={
                    selected
                      ? "var(--sentiment-neutral)"
                      : "var(--accent-primary)"
                  }
                  strokeOpacity={selected ? 1 : 0.38}
                  strokeWidth={1.2 + edge.rule.support * 7}
                  markerEnd="url(#rule-arrow)"
                />
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="transparent"
                  strokeWidth="16"
                  role="button"
                  tabIndex={0}
                  aria-label={`When ${aspectLabel(edge.source.id)} appears, ${aspectLabel(edge.target.id)} also appears in ${percent(edge.rule.confidence)} of those reviews`}
                  onMouseEnter={() => onSelect(edge.rule)}
                  onFocus={() => onSelect(edge.rule)}
                  onClick={() => onSelect(edge.rule)}
                  className="cursor-pointer outline-none"
                />
              </g>
            )
          })}
        </g>
        <g>
          {layout.nodes.map((node) => (
            <g key={node.id} transform={`translate(${node.x} ${node.y})`}>
              <circle
                r={23 + Math.min(node.degree, 8) * 1.4}
                fill="var(--card)"
                stroke="var(--accent-primary)"
                strokeWidth="2"
              />
              <circle r="4" fill="var(--accent-primary)" />
              <text
                y={38 + Math.min(node.degree, 8)}
                textAnchor="middle"
                fill="currentColor"
                className="text-[11px] font-medium"
              >
                {aspectLabel(node.id)}
              </text>
            </g>
          ))}
        </g>
      </svg>
      <div className="border-t px-3 py-2 text-xs text-muted-foreground">
        Arrow = direction · Thicker line = more reviews with both topics
      </div>
    </div>
  )
}

function AssociationMatrix({
  rules,
  selectedKey,
  onSelect,
}: {
  rules: AssociationRule[]
  selectedKey: string | null
  onSelect: (rule: AssociationRule) => void
}) {
  const aspects = Array.from(
    new Set(
      rules.flatMap((rule) => [
        ...rule.antecedent,
        ...rule.consequent,
      ])
    )
  ).sort()
  const lookup = new Map(rules.map((rule) => [ruleKey(rule), rule]))

  return (
    <div className="overflow-auto rounded-xl border bg-background">
      <table className="min-w-[42rem] border-collapse text-xs">
        <caption className="sr-only">
          For each row topic, the percentage of its reviews that also mention
          each column topic
        </caption>
        <thead>
          <tr>
            <th className="sticky left-0 z-10 border-b border-r bg-card p-3 text-left font-medium">
              First topic ↓ / Also mentions →
            </th>
            {aspects.map((aspect) => (
              <th
                key={aspect}
                className="min-w-24 border-b p-2 text-center font-medium"
              >
                {aspectLabel(aspect)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {aspects.map((source) => (
            <tr key={source}>
              <th className="sticky left-0 z-10 border-r bg-card p-3 text-left font-medium">
                {aspectLabel(source)}
              </th>
              {aspects.map((target) => {
                const rule = lookup.get(`${source}→${target}`)
                const selected = rule ? ruleKey(rule) === selectedKey : false
                return (
                  <td key={target} className="border-t p-1 text-center">
                    {source === target ? (
                      <span className="block rounded-md py-3 text-muted-foreground/40">
                        —
                      </span>
                    ) : rule ? (
                      <button
                        type="button"
                        className={cn(
                          "w-full rounded-md px-2 py-3 font-mono transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          selected
                            ? "bg-primary text-primary-foreground"
                            : "bg-primary/10 hover:bg-primary/20"
                        )}
                        onMouseEnter={() => onSelect(rule)}
                        onFocus={() => onSelect(rule)}
                        onClick={() => onSelect(rule)}
                        aria-label={`Of reviews mentioning ${aspectLabel(source)}, ${percent(rule.confidence)} also mention ${aspectLabel(target)}`}
                      >
                        {percent(rule.confidence)}
                      </button>
                    ) : (
                      <span className="block rounded-md py-3 text-muted-foreground/40">
                        ·
                      </span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RuleDetails({
  rule,
  days,
  assumption,
}: {
  rule: AssociationRule | null
  days: number
  assumption?: string
}) {
  if (!rule) {
    return (
      <div className="flex min-h-72 items-center justify-center rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
        Select a connection to inspect it.
      </div>
    )
  }
  const antecedent = rule.antecedent[0]
  const consequent = rule.consequent[0]

  return (
    <aside className="rounded-xl border bg-background p-4">
      <h3 className="text-base font-semibold leading-6">
        {aspectLabel(antecedent)}
        <span className="mx-2 text-primary">→</span>
        {aspectLabel(consequent)}
      </h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        {rule.cooccurrence_count ?? "—"} matching reviews · {percent(rule.support)}{" "}
        with both · {percent(rule.confidence)} also include the second ·{" "}
        {rule.lift.toFixed(2)}× expected
      </p>

      <div className="mt-5">
        <h4 className="text-sm font-semibold">Examples</h4>
        {rule.samples?.length ? (
          <div className="mt-2 space-y-2">
            {rule.samples.map((sample) => {
              const href =
                sample.entity_id != null
                  ? `/entities/${sample.entity_id}?days=${days}&aspect=${encodeURIComponent(antecedent)}&review=${encodeURIComponent(sample.feedback_id)}#reviews`
                  : `/entities?days=${days}`
              return (
                <Link
                  key={sample.feedback_id}
                  href={href}
                  className="group block rounded-lg border p-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <p
                    className="line-clamp-3 text-sm leading-5"
                    {...myanmarLangProps(sample.review_text)}
                  >
                    {sample.review_text || "Review text is unavailable."}
                  </p>
                  <span
                    className="mt-2 flex items-center gap-1 text-xs text-primary"
                    {...myanmarLangProps(sample.entity_name)}
                  >
                    {sample.entity_name || "Open reviews"}
                    <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </span>
                </Link>
              )
            })}
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            No examples available.
          </p>
        )}
      </div>

      <details className="mt-4 border-t pt-3 text-xs text-muted-foreground">
        <summary className="cursor-pointer font-medium text-foreground">
          Metric help
        </summary>
        <p className="mt-2 leading-5">
          “Both topics together” is their share of all reviews. “Second topic
          also appears” is the share of first-topic reviews that also contain
          the second. Above 1× expected means the topics occur together more
          often than chance.
        </p>
        {assumption && <p className="mt-2 leading-5">{assumption}</p>}
      </details>
    </aside>
  )
}

export function AssociationRulesPanel({
  entityId,
  compareIds,
  days,
}: AssociationRulesPanelProps) {
  const [view, setView] = useState<"network" | "matrix">("network")
  const [supportDraft, setSupportDraft] = useState(0.05)
  const [confidenceDraft, setConfidenceDraft] = useState(0.2)
  const [thresholds, setThresholds] = useState({
    support: 0.05,
    confidence: 0.2,
  })
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const entityIds = useMemo(
    () =>
      entityId == null
        ? []
        : [entityId, ...compareIds.filter((id) => id !== entityId)],
    [compareIds, entityId]
  )
  const path = useMemo(() => {
    const params = new URLSearchParams({
      days: String(days),
      min_support: String(thresholds.support),
      min_confidence: String(thresholds.confidence),
    })
    if (entityIds.length) params.set("entity_ids", entityIds.join(","))
    return `/api/mining/association-rules?${params}`
  }, [days, entityIds, thresholds])
  const query = useApi<AssociationRuleResponse>(path)
  const rules = query.data?.rules ?? []
  const selectedRule =
    rules.find((rule) => ruleKey(rule) === selectedKey) ?? rules[0] ?? null

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-5">
          <div className="flex justify-end">
            <div className="flex rounded-lg border bg-background p-1">
              <Button
                type="button"
                size="sm"
                variant={view === "network" ? "secondary" : "ghost"}
                onClick={() => setView("network")}
                aria-pressed={view === "network"}
              >
                <Network className="h-4 w-4" aria-hidden="true" />
                Map
              </Button>
              <Button
                type="button"
                size="sm"
                variant={view === "matrix" ? "secondary" : "ghost"}
                onClick={() => setView("matrix")}
                aria-pressed={view === "matrix"}
              >
                <Grid3X3 className="h-4 w-4" aria-hidden="true" />
                Table
              </Button>
            </div>
          </div>
          <div className="mt-4 rounded-xl border bg-muted/20 p-4">
            <div className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
              <label className="space-y-2 text-sm">
                <span className="flex items-center justify-between gap-3">
                  <span className="font-medium">Both topics together</span>
                  <output className="font-mono text-xs text-muted-foreground">
                    {percent(supportDraft)}
                  </output>
                </span>
                <input
                  type="range"
                  min="0.01"
                  max="0.5"
                  step="0.01"
                  value={supportDraft}
                  onChange={(event) => setSupportDraft(Number(event.target.value))}
                  aria-label="Minimum share of reviews that mention both topics"
                  className="h-8 w-full cursor-pointer accent-[var(--accent-primary)]"
                />
              </label>
              <label className="space-y-2 text-sm">
                <span className="flex items-center justify-between gap-3">
                  <span className="font-medium">Second topic also appears</span>
                  <output className="font-mono text-xs text-muted-foreground">
                    {percent(confidenceDraft)}
                  </output>
                </span>
                <input
                  type="range"
                  min="0.05"
                  max="1"
                  step="0.05"
                  value={confidenceDraft}
                  onChange={(event) =>
                    setConfidenceDraft(Number(event.target.value))
                  }
                  aria-label="Minimum rate at which the second topic appears with the first"
                  className="h-8 w-full cursor-pointer accent-[var(--accent-primary)]"
                />
              </label>
              <Button
                type="button"
                className="min-h-11"
                onClick={() =>
                  setThresholds({
                    support: supportDraft,
                    confidence: confidenceDraft,
                  })
                }
                disabled={
                  supportDraft === thresholds.support &&
                  confidenceDraft === thresholds.confidence
                }
              >
                <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
                Update
              </Button>
            </div>
          </div>

          {query.loading ? (
            <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_19rem]">
              <Skeleton className="h-[28rem] w-full rounded-xl" />
              <Skeleton className="h-[28rem] w-full rounded-xl" />
            </div>
          ) : query.error ? (
            <div className="mt-4">
              <DataError message={query.error} onRetry={query.refetch} />
            </div>
          ) : rules.length ? (
            <>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Badge variant="secondary">
                  {rules.length} {rules.length === 1 ? "pattern" : "patterns"}
                </Badge>
                {query.data?.meta && (
                  <>
                    <Badge variant="outline">
                      {query.data.meta.total_transactions.toLocaleString()}{" "}
                      reviews
                    </Badge>
                    <Badge variant="outline">
                      {query.data.meta.multi_aspect_transactions.toLocaleString()}{" "}
                      with 2+ topics
                    </Badge>
                  </>
                )}
              </div>
              {query.data?.meta && !query.data.meta.sufficient_data && (
                <div
                  className="mt-4 flex gap-3 rounded-lg border border-sentiment-neutral/30 bg-sentiment-neutral/10 p-3 text-sm"
                  role="status"
                >
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-sentiment-neutral-foreground"
                    aria-hidden="true"
                  />
                  <p>
                    Early signal: {query.data.meta.total_transactions} of{" "}
                    {query.data.meta.minimum_transactions} recommended reviews.
                  </p>
                </div>
              )}
              <div className="mt-4 grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
                {view === "network" ? (
                  <AssociationNetwork
                    rules={rules}
                    selectedKey={selectedRule ? ruleKey(selectedRule) : null}
                    onSelect={(rule) => setSelectedKey(ruleKey(rule))}
                  />
                ) : (
                  <AssociationMatrix
                    rules={rules}
                    selectedKey={selectedRule ? ruleKey(selectedRule) : null}
                    onSelect={(rule) => setSelectedKey(ruleKey(rule))}
                  />
                )}
                <RuleDetails
                  rule={selectedRule}
                  days={days}
                  assumption={query.data?.meta?.assumption}
                />
              </div>
            </>
          ) : (
            <div className="mt-4 flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed p-8 text-center">
              <Network className="h-7 w-7 text-muted-foreground" aria-hidden="true" />
              <h3 className="mt-3 font-medium">No patterns found</h3>
              <p className="mt-1 max-w-md text-sm text-muted-foreground">
                Lower the two minimums above, widen the date range, or include
                more entities with analyzed reviews.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
