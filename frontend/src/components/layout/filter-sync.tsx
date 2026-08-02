"use client"

import { useEffect, useRef, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import {
  FILTER_PARAM_KEYS,
  useFilterStore,
  filtersToSearchParams,
  filtersFromSearchParams,
  hasActiveFilters,
  type FilterValues,
} from "@/lib/stores/filters"

function sameFilters(left: FilterValues, right: FilterValues): boolean {
  return (
    left.entityId === right.entityId &&
    left.days === right.days &&
    left.aspect === right.aspect
  )
}

/** Replace only global-filter keys while retaining route-specific parameters. */
function mergeFiltersIntoCurrentUrl(values: FilterValues): string {
  const merged = new URLSearchParams(window.location.search)
  for (const key of FILTER_PARAM_KEYS) merged.delete(key)
  filtersToSearchParams(values).forEach((value, key) => {
    merged.set(key, value)
  })
  return merged.toString()
}

/**
 * Two-way sync between the global filter store and URL search params
 * (v3 spec §4: filtered views must be bookmarkable/shareable).
 *
 * - Initial URL → store: a shared/bookmarked URL is authoritative.
 * - In-app navigation: clean destination URLs inherit the sticky store values.
 * - Store → URL: merge global-filter keys without deleting page-specific keys.
 *
 * Both directions compare serialized values first, so neither can loop.
 * Must be rendered inside a <Suspense> boundary (useSearchParams).
 */
export function FilterSync({ children }: { children: React.ReactNode }) {
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  const initialized = useRef(false)
  const [ready, setReady] = useState(false)

  // URL → store
  useEffect(() => {
    const fromUrl = filtersFromSearchParams(searchParams)
    const current = useFilterStore.getState()
    const urlHasFilters = FILTER_PARAM_KEYS.some((key) => searchParams.has(key))

    // The first URL is authoritative, including a clean URL that resets all
    // filters. On later route changes, a URL without global-filter keys keeps
    // the current sticky filters and receives them below.
    if (!initialized.current) {
      initialized.current = true
      if (!sameFilters(fromUrl, current)) {
        useFilterStore.getState().hydrate(fromUrl)
      }
      const canonical = mergeFiltersIntoCurrentUrl(fromUrl)
      const live = new URLSearchParams(window.location.search).toString()
      if (canonical !== live) {
        router.replace(canonical ? `${pathname}?${canonical}` : pathname, {
          scroll: false,
        })
      }
      setReady(true)
      return
    }

    if (urlHasFilters) {
      if (!sameFilters(fromUrl, current)) {
        useFilterStore.getState().hydrate(fromUrl)
      }
      return
    }

    if (hasActiveFilters(current)) {
      const next = mergeFiltersIntoCurrentUrl(current)
      const live = new URLSearchParams(window.location.search).toString()
      if (next !== live) {
        router.replace(next ? `${pathname}?${next}` : pathname, {
          scroll: false,
        })
      }
    } else if (!sameFilters(fromUrl, current)) {
      useFilterStore.getState().hydrate(fromUrl)
    }
  }, [searchParams, router, pathname])

  // Store → URL
  useEffect(() => {
    const unsubscribe = useFilterStore.subscribe((state) => {
      const next = mergeFiltersIntoCurrentUrl(state)
      // Read the live URL (not the render-time snapshot) to avoid races.
      const current = new URLSearchParams(window.location.search).toString()
      if (next !== current) {
        router.replace(next ? `${pathname}?${next}` : pathname, {
          scroll: false,
        })
      }
    })
    return unsubscribe
  }, [router, pathname])

  return ready ? children : null
}
