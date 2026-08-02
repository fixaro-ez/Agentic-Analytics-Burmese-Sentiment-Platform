"use client"

import { useQuery, type UseQueryOptions } from "@tanstack/react-query"
import { api } from "@/lib/api"

interface UseApiOptions<T> {
  initialData?: T
  skip?: boolean
  /**
   * Polling interval passthrough to TanStack Query. Accepts a number (ms),
   * false, or a callback receiving the query — return false to stop polling
   * (e.g. once a background job reaches a terminal status).
   */
  refetchInterval?: UseQueryOptions<T, Error>["refetchInterval"]
}

interface UseApiResult<T> {
  data: T | undefined
  loading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Server-state hook backed by TanStack Query: response caching (shared
 * across pages via the global QueryClient), stale-while-revalidate, and
 * optional polling. Public API is unchanged from the previous hand-rolled
 * implementation, so existing call sites keep working.
 */
export function useApi<T>(
  path: string,
  options: UseApiOptions<T> = {}
): UseApiResult<T> {
  const { initialData, skip = false, refetchInterval } = options

  const query = useQuery<T, Error>({
    queryKey: ["api", path],
    queryFn: () => api.get<T>(path),
    enabled: !skip,
    initialData,
    refetchInterval,
  })

  return {
    data: query.data,
    // Only "loading" when actually fetching the first page of data; skipped
    // queries and background refetches with cached data are not loading.
    loading: !skip && query.isPending,
    error: query.error ? query.error.message : null,
    refetch: () => {
      void query.refetch()
    },
  }
}
