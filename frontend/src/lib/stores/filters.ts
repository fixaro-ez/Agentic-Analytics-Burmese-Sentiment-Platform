import { create } from "zustand"

const FILTER_ASPECTS = new Set([
  "product_quality",
  "fulfillment_and_speed",
  "price_and_value",
  "staff_and_service",
  "variety_and_availability",
])

/**
 * Global filter state (v3 spec §4): entity selection, date range, and aspect.
 *
 * State is mirrored to URL search params by <FilterSync /> so filtered views
 * are bookmarkable/shareable. IDs are stored (not names); display names are
 * resolved from the entities query at render time.
 */

export const DEFAULT_DAYS = 30
export const DATE_RANGE_PRESETS = [7, 30, 90] as const
export const FILTER_PARAM_KEYS = ["entity", "days", "aspect"] as const

export interface FilterValues {
  entityId: number | null
  days: number
  /** Cross-chart aspect filter (set by clicking aspect bars/drivers/radar axes). */
  aspect: string | null
}

interface FilterState extends FilterValues {
  setEntity: (id: number | null) => void
  setDays: (days: number) => void
  setAspect: (aspect: string | null) => void
  clearFilters: () => void
  /** Replace all values at once (used by URL → store hydration). */
  hydrate: (values: FilterValues) => void
}

export const DEFAULT_FILTER_VALUES: FilterValues = {
  entityId: null,
  days: DEFAULT_DAYS,
  aspect: null,
}

export const useFilterStore = create<FilterState>()((set) => ({
  ...DEFAULT_FILTER_VALUES,

  setEntity: (id) => set({ entityId: id }),

  setDays: (days) =>
    set({ days: Math.min(365, Math.max(1, Math.trunc(days) || DEFAULT_DAYS)) }),

  setAspect: (aspect) => set({ aspect: aspect || null }),

  clearFilters: () => set({ ...DEFAULT_FILTER_VALUES }),

  hydrate: (values) =>
    set({
      entityId: values.entityId,
      days: Math.min(
        365,
        Math.max(1, Math.trunc(values.days) || DEFAULT_DAYS)
      ),
      aspect: values.aspect || null,
    }),
}))

// ---------- URL (de)serialization ----------

interface SearchParamsLike {
  get(name: string): string | null
}

function parsePositiveInt(raw: string | null): number | null {
  if (!raw) return null
  const n = Number(raw)
  return Number.isInteger(n) && n > 0 ? n : null
}

/** Store values → URL params. Defaults are omitted to keep URLs clean. */
export function filtersToSearchParams(values: FilterValues): URLSearchParams {
  const params = new URLSearchParams()
  if (values.entityId != null) params.set("entity", String(values.entityId))
  if (values.days !== DEFAULT_DAYS) params.set("days", String(values.days))
  if (values.aspect) params.set("aspect", values.aspect)
  return params
}

/** URL params → store values. Unknown/invalid params fall back to defaults. */
export function filtersFromSearchParams(params: SearchParamsLike): FilterValues {
  const entityId = parsePositiveInt(params.get("entity"))

  const parsedDays = parsePositiveInt(params.get("days"))
  const days =
    parsedDays != null ? Math.min(365, Math.max(1, parsedDays)) : DEFAULT_DAYS

  const rawAspect = params.get("aspect")?.trim() || null
  const aspect = rawAspect && FILTER_ASPECTS.has(rawAspect) ? rawAspect : null

  return { entityId, days, aspect }
}

/** True when any filter differs from defaults (drives breadcrumb/clear UI). */
export function hasActiveFilters(values: FilterValues): boolean {
  return (
    values.entityId != null ||
    values.days !== DEFAULT_DAYS ||
    values.aspect != null
  )
}
