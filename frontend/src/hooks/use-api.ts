"use client"

import { useState, useEffect, useCallback } from "react"
import { api } from "@/lib/api"

interface UseApiOptions<T> {
  initialData?: T
  skip?: boolean
}

interface UseApiResult<T> {
  data: T | undefined
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useApi<T>(
  path: string,
  options: UseApiOptions<T> = {}
): UseApiResult<T> {
  const { initialData, skip = false } = options
  const [requestVersion, setRequestVersion] = useState(0)
  const [state, setState] = useState<{
    path: string
    version: number
    data: T | undefined
    error: string | null
  }>({
    path,
    version: -1,
    data: initialData,
    error: null,
  })

  useEffect(() => {
    if (skip) return
    let cancelled = false

    api.get<T>(path).then(
      (result) => {
        if (!cancelled) {
          setState({ path, version: requestVersion, data: result, error: null })
        }
      },
      (err) => {
        if (!cancelled) {
          setState({
            path,
            version: requestVersion,
            data: undefined,
            error: err instanceof Error ? err.message : "Unknown error",
          })
        }
      }
    )

    return () => {
      cancelled = true
    }
  }, [path, requestVersion, skip])

  const refetch = useCallback(() => {
    setRequestVersion((version) => version + 1)
  }, [])

  const requestIsCurrent =
    state.path === path && state.version === requestVersion

  return {
    data: state.data,
    loading: !skip && !requestIsCurrent,
    error: requestIsCurrent ? state.error : null,
    refetch,
  }
}
