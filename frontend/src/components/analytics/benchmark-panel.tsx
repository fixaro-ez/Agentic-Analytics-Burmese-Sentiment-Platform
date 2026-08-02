"use client"

import Link from "next/link"
import { useMemo, useState } from "react"
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Info,
} from "lucide-react"

import {
  BranchSelector,
  BrandSelect,
  DaysSelect,
} from "@/components/analytics/brand-analysis-selectors"
import { ShareOfVoiceDonut } from "@/components/charts/share-of-voice-donut"
import { DataError } from "@/components/data-error"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useBrands, useCompetitorBenchmark } from "@/hooks/use-analytics"
import { benchmarkResponseState } from "@/lib/benchmark-helpers"
import type { BenchmarkInsight } from "@/lib/types"
import { ASPECT_LABELS } from "@/lib/types"
import { cn } from "@/lib/utils"

export function BenchmarkPanel() {
  const brandsQuery = useBrands()
  const brands = useMemo(() => brandsQuery.data?.brands ?? [], [brandsQuery.data])
  const [brandASelection, setBrandASelection] = useState<{
    brandId: number
    branches: number[]
  } | null>(null)
  const [brandBSelection, setBrandBSelection] = useState<{
    brandId: number
    branches: number[]
  } | null>(null)
  const [days, setDays] = useState(30)

  const brandAId = brandASelection?.brandId ?? brands[0]?.brand_id ?? null
  const brandBId = brandBSelection?.brandId ?? brands[1]?.brand_id ?? null
  const brandA = brands.find((brand) => brand.brand_id === brandAId)
  const brandB = brands.find((brand) => brand.brand_id === brandBId)
  const brandABranches =
    brandASelection?.brandId === brandAId
      ? brandASelection.branches
      : brandA?.foodpanda_shops.map((shop) => shop.entity_id) ?? []
  const brandBBranches =
    brandBSelection?.brandId === brandBId
      ? brandBSelection.branches
      : brandB?.foodpanda_shops.map((shop) => shop.entity_id) ?? []

  function chooseBrandA(nextId: number) {
    const next = brands.find((brand) => brand.brand_id === nextId)
    setBrandASelection({
      brandId: nextId,
      branches: next?.foodpanda_shops.map((shop) => shop.entity_id) ?? [],
    })
  }

  function chooseBrandB(nextId: number) {
    const next = brands.find((brand) => brand.brand_id === nextId)
    setBrandBSelection({
      brandId: nextId,
      branches: next?.foodpanda_shops.map((shop) => shop.entity_id) ?? [],
    })
  }

  const ready =
    brandAId != null &&
    brandBId != null &&
    brandAId !== brandBId &&
    brandABranches.length > 0 &&
    brandBBranches.length > 0
  const benchmark = useCompetitorBenchmark(
    brandAId,
    brandBId,
    brandABranches,
    brandBBranches,
    days,
    { skip: !ready }
  )
  const state = benchmarkResponseState(benchmark.data)
  const aspectNames = useMemo(
    () => [...new Set((benchmark.data?.aspects ?? []).map((item) => item.aspect))],
    [benchmark.data]
  )

  if (brandsQuery.loading) {
    return <Skeleton className="h-[34rem] w-full" />
  }
  if (brandsQuery.error) {
    return <DataError message={brandsQuery.error} onRetry={brandsQuery.refetch} />
  }
  if (brands.length < 2) {
    return (
      <Card>
        <CardContent className="flex min-h-72 flex-col items-center justify-center p-8 text-center">
          <h2 className="text-lg font-semibold">Map two brands first</h2>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            A benchmark compares one explicit brand mapping against one other
            brand mapping.
          </p>
          <Button asChild className="mt-5">
            <Link href="/entities#brand-mappings">Open Brand Mapping</Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Head-to-head setup</CardTitle>
          <CardDescription>
            Choose both brands, their branches, and the comparison period here.
            All mapped branches are selected initially.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-[1fr_1fr_180px]">
          <div className="space-y-4 rounded-xl border p-4">
            <BrandSelect
              label="Your brand"
              brands={brands}
              value={brandAId}
              exclude={brandBId}
              onChange={chooseBrandA}
            />
            <BranchSelector
              brand={brandA}
              selected={brandABranches}
              onChange={(branches) =>
                brandAId != null &&
                setBrandASelection({ brandId: brandAId, branches })
              }
            />
          </div>
          <div className="space-y-4 rounded-xl border p-4">
            <BrandSelect
              label="Competitor"
              brands={brands}
              value={brandBId}
              exclude={brandAId}
              onChange={chooseBrandB}
            />
            <BranchSelector
              brand={brandB}
              selected={brandBBranches}
              onChange={(branches) =>
                brandBId != null &&
                setBrandBSelection({ brandId: brandBId, branches })
              }
            />
          </div>
          <DaysSelect value={days} onChange={setDays} />
        </CardContent>
      </Card>

      {!ready ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            Select two different brands and at least one branch for each.
          </CardContent>
        </Card>
      ) : benchmark.loading ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      ) : benchmark.error ? (
        <DataError message={benchmark.error} onRetry={benchmark.refetch} />
      ) : !benchmark.data ? null : (
        <>
          {state !== "ready" && (
            <div className="flex items-start gap-3 rounded-xl border border-sentiment-neutral/35 bg-sentiment-neutral/[0.05] p-4">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-sentiment-neutral-foreground" />
              <div>
                <p className="font-medium">Review minimum not met</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Both brands need {benchmark.data.meta.minimum_reviews} distinct
                  Foodpanda reviews. Unreliable sentiment values and comparison
                  conclusions are hidden.
                </p>
              </div>
            </div>
          )}

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Combined share of voice</CardTitle>
                <CardDescription>
                  Equal-weight blend of Facebook weighted engagement and
                  Foodpanda review volume
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ShareOfVoiceDonut brands={benchmark.data.brands} />
                <div className="grid gap-3 sm:grid-cols-2">
                  {benchmark.data.brands.map((brand) => (
                    <div key={brand.brand_id} className="rounded-lg border p-3">
                      <p className="font-medium">{brand.brand_name}</p>
                      <dl className="mt-3 space-y-2 text-xs">
                        <Metric label="Facebook share" value={percent(brand.facebook_share)} />
                        <Metric label="Foodpanda share" value={percent(brand.foodpanda_share)} />
                        <Metric label="Posts" value={brand.facebook_post_count.toLocaleString()} />
                        <Metric label="Reviews" value={brand.review_count.toLocaleString()} />
                      </dl>
                      {!brand.eligible && (
                        <p className="mt-3 text-xs text-sentiment-neutral-foreground">
                          {brand.warning}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Aspect sentiment matrix</CardTitle>
                <CardDescription>
                  Foodpanda ABSA net sentiment by selected brand branches
                </CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                {aspectNames.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Aspect</TableHead>
                        {benchmark.data.brands.map((brand) => (
                          <TableHead key={brand.brand_id} className="text-right">
                            {brand.brand_name}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {aspectNames.map((aspect) => (
                        <TableRow key={aspect}>
                          <TableCell>
                            {ASPECT_LABELS[aspect] ?? aspect}
                          </TableCell>
                          {benchmark.data!.brands.map((brand) => {
                            const cell = benchmark.data!.aspects.find(
                              (item) =>
                                item.brand_id === brand.brand_id &&
                                item.aspect === aspect
                            )
                            return (
                              <TableCell
                                key={brand.brand_id}
                                className="text-right font-mono"
                              >
                                {cell?.net_sentiment == null
                                  ? "—"
                                  : percent(cell.net_sentiment, true)}
                              </TableCell>
                            )
                          })}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="py-20 text-center text-sm text-muted-foreground">
                    No aspect observations match this selection.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Advantages and vulnerabilities</CardTitle>
              <CardDescription>
                Only head-to-head gaps of at least 10 percentage points are shown
              </CardDescription>
            </CardHeader>
            <CardContent>
              {benchmark.data.insights.length ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {benchmark.data.insights.map((insight) => (
                    <Insight
                      key={`${insight.aspect}-${insight.kind}`}
                      insight={insight}
                    />
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                  {benchmark.data.meta.sufficient_data
                    ? "No aspect gap reaches the 10-point threshold."
                    : "Insights remain hidden until both brands pass the review guard."}
                </p>
              )}
            </CardContent>
          </Card>

          <details className="rounded-xl border bg-card px-4 py-3 text-sm">
            <summary className="cursor-pointer font-medium">Metric assumptions</summary>
            <ul className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
              {benchmark.data.meta.assumptions.map((assumption) => (
                <li key={assumption} className="flex gap-2">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {assumption}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono font-medium">{value}</dd>
    </div>
  )
}

function percent(value: number | null, signed = false) {
  if (value == null) return "—"
  const prefix = signed && value > 0 ? "+" : ""
  return `${prefix}${(value * 100).toFixed(1)}%`
}

function Insight({ insight }: { insight: BenchmarkInsight }) {
  const advantage = insight.kind === "advantage"
  const Icon = advantage ? ArrowUpRight : ArrowDownRight
  return (
    <article
      className={cn(
        "rounded-xl border p-4",
        advantage
          ? "border-sentiment-positive/30 bg-sentiment-positive/[0.04]"
          : "border-sentiment-negative/30 bg-sentiment-negative/[0.04]"
      )}
    >
      <div className="flex items-center justify-between">
        <Badge variant="outline">
          {advantage ? "Advantage" : "Vulnerability"}
        </Badge>
        <Icon className="h-5 w-5" />
      </div>
      <p className="mt-4 font-medium">
        {ASPECT_LABELS[insight.aspect] ?? insight.aspect}
      </p>
      <p className="mt-2 font-mono text-xl font-semibold">
        {percent(insight.delta, true)}
      </p>
    </article>
  )
}
