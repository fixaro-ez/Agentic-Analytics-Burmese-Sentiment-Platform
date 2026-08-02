import type { BenchmarkResponse } from "@/lib/types"

export type BenchmarkResponseState =
  | "empty"
  | "insufficient"
  | "partial"
  | "ready"

export function benchmarkResponseState(
  response: BenchmarkResponse | undefined
): BenchmarkResponseState {
  if (!response || response.brands.length === 0) return "empty"
  if (response.meta.eligible_brand_count === 0) return "insufficient"
  if (response.meta.eligible_brand_count < 2) return "partial"
  return "ready"
}
