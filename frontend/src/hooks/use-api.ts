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
  const [data, setData] = useState<T | undefined>(options.initialData)
  const [loading, setLoading] = useState(!options.skip)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (options.skip) return
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<T>(path)
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [path, options.skip])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { data, loading, error, refetch: fetchData }
}
