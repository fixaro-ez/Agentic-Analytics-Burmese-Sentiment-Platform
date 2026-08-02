"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  Boxes,
  ExternalLink,
  GitBranch,
  ScatterChart,
} from "lucide-react"

import { DataError } from "@/components/data-error"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/use-api"
import {
  convexHull,
  formatMiningMetric,
  MINING_AXIS_LABELS,
  miningMetricValue,
  type PlotPoint,
} from "@/lib/mining-visuals"
import { myanmarLangProps } from "@/lib/myanmar"
import type {
  ClusterAlgorithm,
  EntityCluster,
  EntityClusterMember,
  EntityClusterResponse,
  MiningAxis,
} from "@/lib/types"

interface EntityClustersPanelProps {
  entityId: number | null
  compareIds: number[]
  days: number
}

const AXES = Object.keys(MINING_AXIS_LABELS) as MiningAxis[]
const CLUSTER_COLORS = [
  "var(--entity-self)",
  "var(--entity-compare-1)",
  "var(--entity-compare-2)",
  "var(--sentiment-positive)",
  "var(--sentiment-neutral)",
  "var(--sentiment-negative)",
]

interface Scale {
  min: number
  max: number
  map: (value: number) => number
}

function makeScale(
  values: number[],
  outputStart: number,
  outputEnd: number,
  boundedRatio: boolean
): Scale {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const padding = max === min ? Math.max(Math.abs(max) * 0.1, 0.1) : 0
  const domainMin = boundedRatio ? Math.max(0, min - padding) : min - padding
  const domainMax = boundedRatio ? Math.min(1, max + padding) : max + padding
  return {
    min: domainMin,
    max: domainMax,
    map: (value) =>
      outputStart +
      ((value - domainMin) / Math.max(domainMax - domainMin, Number.EPSILON)) *
        (outputEnd - outputStart),
  }
}

function tickValues(scale: Scale) {
  return Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4
    return scale.min + (scale.max - scale.min) * ratio
  })
}

function EntityScatterPlot({
  clusters,
  xAxis,
  yAxis,
  selectedEntityId,
  onSelect,
}: {
  clusters: EntityCluster[]
  xAxis: MiningAxis
  yAxis: MiningAxis
  selectedEntityId: number | null
  onSelect: (entity: EntityClusterMember) => void
}) {
  const width = 780
  const height = 440
  const margin = { left: 74, right: 28, top: 26, bottom: 64 }
  const allEntities = clusters.flatMap((cluster) => cluster.entities)
  const xScale = makeScale(
    allEntities.map((entity) => miningMetricValue(entity, xAxis)),
    margin.left,
    width - margin.right,
    xAxis !== "total_reviews"
  )
  const yScale = makeScale(
    allEntities.map((entity) => miningMetricValue(entity, yAxis)),
    height - margin.bottom,
    margin.top,
    yAxis !== "total_reviews"
  )

  const plotClusters = clusters.map((cluster, index) => {
    const points: PlotPoint[] = cluster.entities.map((entity) => ({
      x: xScale.map(miningMetricValue(entity, xAxis)),
      y: yScale.map(miningMetricValue(entity, yAxis)),
      entity,
    }))
    return {
      cluster,
      color: CLUSTER_COLORS[index % CLUSTER_COLORS.length],
      points,
      hull: convexHull(points),
    }
  })

  return (
    <div className="overflow-x-auto rounded-xl border bg-background">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="block min-h-[25rem] min-w-[42rem] w-full"
        role="img"
        aria-label={`Entity comparison chart using ${MINING_AXIS_LABELS[xAxis]} and ${MINING_AXIS_LABELS[yAxis]}`}
      >
        {tickValues(xScale).map((tick) => {
          const x = xScale.map(tick)
          return (
            <g key={`x-${tick}`}>
              <line
                x1={x}
                x2={x}
                y1={margin.top}
                y2={height - margin.bottom}
                stroke="var(--border)"
                strokeDasharray="3 5"
              />
              <text
                x={x}
                y={height - margin.bottom + 22}
                textAnchor="middle"
                fill="var(--muted-foreground)"
                className="text-[11px]"
              >
                {formatMiningMetric(tick, xAxis)}
              </text>
            </g>
          )
        })}
        {tickValues(yScale).map((tick) => {
          const y = yScale.map(tick)
          return (
            <g key={`y-${tick}`}>
              <line
                x1={margin.left}
                x2={width - margin.right}
                y1={y}
                y2={y}
                stroke="var(--border)"
                strokeDasharray="3 5"
              />
              <text
                x={margin.left - 12}
                y={y + 4}
                textAnchor="end"
                fill="var(--muted-foreground)"
                className="text-[11px]"
              >
                {formatMiningMetric(tick, yAxis)}
              </text>
            </g>
          )
        })}

        {plotClusters.map(({ cluster, color, hull }) =>
          hull.length >= 3 ? (
            <path
              key={`hull-${cluster.cluster_id}`}
              d={`${hull
                .map(
                  (point, index) =>
                    `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`
                )
                .join(" ")} Z`}
              fill={color}
              fillOpacity="0.1"
              stroke={color}
              strokeOpacity="0.8"
              strokeWidth="2"
              strokeLinejoin="round"
            />
          ) : null
        )}

        {plotClusters.flatMap(({ cluster, color, points }) =>
          points.map((point) => {
            const selected = point.entity.entity_id === selectedEntityId
            const radius =
              7 +
              Math.min(
                7,
                Math.log10(Math.max(point.entity.total_reviews, 1)) * 2
              )
            return (
              <g
                key={`${cluster.cluster_id}-${point.entity.entity_id}`}
                transform={`translate(${point.x} ${point.y})`}
                role="button"
                tabIndex={0}
                aria-label={`${point.entity.entity_name}, ${MINING_AXIS_LABELS[xAxis]} ${formatMiningMetric(miningMetricValue(point.entity, xAxis), xAxis)}, ${MINING_AXIS_LABELS[yAxis]} ${formatMiningMetric(miningMetricValue(point.entity, yAxis), yAxis)}`}
                onMouseEnter={() => onSelect(point.entity)}
                onFocus={() => onSelect(point.entity)}
                onClick={() => onSelect(point.entity)}
                className="cursor-pointer outline-none"
              >
                <circle
                  r={selected ? radius + 5 : radius}
                  fill={color}
                  fillOpacity={selected ? 1 : 0.82}
                  stroke={selected ? "var(--foreground)" : "var(--card)"}
                  strokeWidth={selected ? 2.5 : 2}
                />
                <text
                  y={-radius - 7}
                  textAnchor="middle"
                  fill="currentColor"
                  className="text-[11px] font-medium"
                >
                  {point.entity.entity_name}
                </text>
              </g>
            )
          })
        )}

        <text
          x={(margin.left + width - margin.right) / 2}
          y={height - 14}
          textAnchor="middle"
          fill="var(--foreground)"
          className="text-xs font-medium"
        >
          {MINING_AXIS_LABELS[xAxis]}
        </text>
        <text
          transform={`translate(18 ${(margin.top + height - margin.bottom) / 2}) rotate(-90)`}
          textAnchor="middle"
          fill="var(--foreground)"
          className="text-xs font-medium"
        >
          {MINING_AXIS_LABELS[yAxis]}
        </text>
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-2 border-t px-4 py-3">
        {clusters.map((cluster, index) => (
          <span key={cluster.cluster_id} className="flex items-center gap-2 text-xs">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{
                backgroundColor:
                  CLUSTER_COLORS[index % CLUSTER_COLORS.length],
              }}
              aria-hidden="true"
            />
            {cluster.label.replace(/^Cluster/i, "Group")} · {cluster.entities.length}
          </span>
        ))}
      </div>
    </div>
  )
}

function EntityDetails({
  entity,
  cluster,
  xAxis,
  yAxis,
  days,
}: {
  entity: EntityClusterMember | null
  cluster: EntityCluster | null
  xAxis: MiningAxis
  yAxis: MiningAxis
  days: number
}) {
  if (!entity) {
    return (
      <aside className="flex min-h-72 items-center justify-center rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
        Select a dot to compare that entity with the rest of its group.
      </aside>
    )
  }

  const profileAxes = Array.from(
    new Set<MiningAxis>([
      xAxis,
      yAxis,
      "positive_ratio",
      "negative_ratio",
      "avg_confidence",
    ])
  )

  return (
    <aside className="rounded-xl border bg-background p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className="text-base font-semibold"
            {...myanmarLangProps(entity.entity_name)}
          >
            {entity.entity_name}
          </h3>
          <p className="mt-1 text-xs capitalize text-muted-foreground">
            {entity.platform}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <Badge variant="secondary">
            {cluster?.label.replace(/^Cluster/i, "Group") ?? "Entity profile"}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {entity.total_reviews} reviews
          </span>
        </div>
      </div>
      <dl className="mt-4 space-y-3">
        {profileAxes.map((axis) => (
          <div
            key={axis}
            className="flex items-center justify-between gap-4 border-b pb-2 text-sm last:border-0"
          >
            <dt className="text-muted-foreground">{MINING_AXIS_LABELS[axis]}</dt>
            <dd className="font-mono font-medium">
              {formatMiningMetric(miningMetricValue(entity, axis), axis)}
            </dd>
          </div>
        ))}
      </dl>
      <Button asChild variant="outline" className="mt-5 w-full">
        <Link href={`/entities/${entity.entity_id}?days=${days}#reviews`}>
          View reviews
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
        </Link>
      </Button>
    </aside>
  )
}

export function EntityClustersPanel({
  entityId,
  compareIds,
  days,
}: EntityClustersPanelProps) {
  const [algorithm, setAlgorithm] = useState<ClusterAlgorithm>("kmeans")
  const [k, setK] = useState(3)
  const [xAxis, setXAxis] = useState<MiningAxis>("positive_ratio")
  const [yAxis, setYAxis] = useState<MiningAxis>("negative_ratio")
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null)
  const entityIds = useMemo(
    () =>
      entityId == null
        ? []
        : [entityId, ...compareIds.filter((id) => id !== entityId)],
    [compareIds, entityId]
  )
  const effectiveK = algorithm === "hierarchical" ? 3 : k
  const path = useMemo(() => {
    const params = new URLSearchParams({
      days: String(days),
      algorithm,
      k: String(effectiveK),
      x_axis: xAxis,
      y_axis: yAxis,
    })
    if (entityIds.length) params.set("entity_ids", entityIds.join(","))
    return `/api/mining/clusters?${params}`
  }, [algorithm, days, effectiveK, entityIds, xAxis, yAxis])
  const query = useApi<EntityClusterResponse>(path)
  const clusters = query.data?.clusters ?? []
  const allEntities = clusters.flatMap((cluster) => cluster.entities)
  const selectedEntity =
    allEntities.find((entity) => entity.entity_id === selectedEntityId) ??
    allEntities[0] ??
    null
  const selectedCluster =
    clusters.find((cluster) =>
      cluster.entities.some(
        (entity) => entity.entity_id === selectedEntity?.entity_id
      )
    ) ?? null
  const hasSmallHull = clusters.some(
    (cluster) => cluster.entities.length > 0 && cluster.entities.length < 3
  )

  return (
    <Card>
      <CardContent className="p-5">
        <div className="grid gap-4 rounded-xl border bg-muted/20 p-4 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1.1fr_auto] xl:items-end">
          <div className="space-y-2">
            <span className="text-sm font-medium">Compare by</span>
            <Select
              value={xAxis}
              onValueChange={(value) => setXAxis(value as MiningAxis)}
            >
              <SelectTrigger className="min-h-11" aria-label="Select first comparison measure">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AXES.map((axis) => (
                  <SelectItem key={axis} value={axis} disabled={axis === yAxis}>
                    {MINING_AXIS_LABELS[axis]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <span className="text-sm font-medium">Against</span>
            <Select
              value={yAxis}
              onValueChange={(value) => setYAxis(value as MiningAxis)}
            >
              <SelectTrigger className="min-h-11" aria-label="Select second comparison measure">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AXES.map((axis) => (
                  <SelectItem key={axis} value={axis} disabled={axis === xAxis}>
                    {MINING_AXIS_LABELS[axis]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <span className="text-sm font-medium">Method</span>
            <div className="flex min-h-11 rounded-lg border bg-background p-1">
              <Button
                type="button"
                size="sm"
                className="flex-1"
                variant={algorithm === "kmeans" ? "secondary" : "ghost"}
                onClick={() => setAlgorithm("kmeans")}
                aria-pressed={algorithm === "kmeans"}
                aria-label="Fixed groups using K-Means"
              >
                <Boxes className="h-4 w-4" aria-hidden="true" />
                Fixed groups
              </Button>
              <Button
                type="button"
                size="sm"
                className="flex-1"
                variant={algorithm === "hierarchical" ? "secondary" : "ghost"}
                onClick={() => setAlgorithm("hierarchical")}
                aria-pressed={algorithm === "hierarchical"}
                aria-label="Similarity tree using hierarchical clustering"
              >
                <GitBranch className="h-4 w-4" aria-hidden="true" />
                Similarity tree
              </Button>
            </div>
          </div>
          {algorithm === "kmeans" ? (
            <div className="space-y-2">
              <span className="text-sm font-medium">Groups</span>
              <Select value={String(k)} onValueChange={(value) => setK(Number(value))}>
                <SelectTrigger className="min-h-11 w-full xl:w-28" aria-label="Select number of groups">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[2, 3, 4, 5, 6].map((value) => (
                    <SelectItem key={value} value={String(value)}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="flex min-h-11 items-end pb-3">
              <span className="text-xs text-muted-foreground">Creates 3 groups</span>
            </div>
          )}
        </div>

        {query.loading ? (
          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_19rem]">
            <Skeleton className="h-[30rem] w-full rounded-xl" />
            <Skeleton className="h-[30rem] w-full rounded-xl" />
          </div>
        ) : query.error ? (
          <div className="mt-4">
            <DataError message={query.error} onRetry={query.refetch} />
          </div>
        ) : query.data?.meta && !query.data.meta.sufficient_data ? (
          <div
            className="mt-4 flex min-h-72 flex-col items-center justify-center rounded-xl border border-sentiment-neutral/30 bg-sentiment-neutral/5 p-8 text-center"
            role="status"
          >
            <AlertTriangle
              className="h-7 w-7 text-sentiment-neutral-foreground"
              aria-hidden="true"
            />
            <h3 className="mt-3 font-medium">Not enough entities to form groups</h3>
            <p className="mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
              This filter returns {query.data.meta.total_entities}{" "}
              {query.data.meta.total_entities === 1 ? "entity" : "entities"}.
              The selected configuration needs at least{" "}
              {query.data.meta.minimum_entities}. Add comparison entities,
              choose fewer groups, or widen the date range.
            </p>
            <details className="mt-4 max-w-xl text-xs text-muted-foreground">
              <summary className="cursor-pointer font-medium text-foreground">
                Why more entities are needed
              </summary>
              <p className="mt-2 leading-5">{query.data.meta.assumption}</p>
            </details>
          </div>
        ) : clusters.length ? (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Badge variant="secondary">
                {query.data?.meta?.actual_clusters ?? clusters.length} groups
              </Badge>
              <Badge variant="outline">
                {query.data?.meta?.total_entities ?? allEntities.length} entities
              </Badge>
              <Badge variant="outline" className="capitalize">
                {algorithm === "kmeans" ? "Fixed groups" : "Similarity tree"}
              </Badge>
            </div>
            {hasSmallHull && (
              <div className="mt-4 flex gap-3 rounded-lg border p-3 text-xs text-muted-foreground">
                <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
                Small groups appear as points only.
              </div>
            )}
            <div className="mt-4 grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
              <EntityScatterPlot
                clusters={clusters}
                xAxis={xAxis}
                yAxis={yAxis}
                selectedEntityId={selectedEntity?.entity_id ?? null}
                onSelect={(entity) => setSelectedEntityId(entity.entity_id)}
              />
              <EntityDetails
                entity={selectedEntity}
                cluster={selectedCluster}
                xAxis={xAxis}
                yAxis={yAxis}
                days={days}
              />
            </div>
            {query.data?.meta?.assumption && (
              <details className="mt-4 text-xs text-muted-foreground">
                <summary className="cursor-pointer font-medium text-foreground">
                  How entities are grouped
                </summary>
                <p className="mt-2 max-w-3xl leading-5">
                  Fixed groups uses K-Means; Similarity tree uses hierarchical
                  clustering. {" "}
                  {query.data.meta.assumption}
                </p>
              </details>
            )}
          </>
        ) : (
          <div className="mt-4 flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed p-8 text-center">
            <ScatterChart className="h-7 w-7 text-muted-foreground" aria-hidden="true" />
            <h3 className="mt-3 font-medium">No entities to compare</h3>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              Widen the date range or clear the entity filter to include more
              entities with analyzed reviews.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
