const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
let refreshedAccessToken: { token: string; expiresAt: number } | null = null

async function getAuthHeaders(
  includeContentType = true,
  refresh = false
): Promise<HeadersInit> {
  const { createClient } = await import("@/lib/supabase/client")
  const supabase = createClient()
  if (
    !refresh &&
    refreshedAccessToken &&
    refreshedAccessToken.expiresAt > Date.now() + 30_000
  ) {
    return {
      ...(includeContentType ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${refreshedAccessToken.token}`,
    }
  }
  const { data } = refresh
    ? await supabase.auth.refreshSession()
    : await supabase.auth.getSession()
  const token = data.session?.access_token
  if (refresh && token) {
    refreshedAccessToken = {
      token,
      expiresAt: (data.session?.expires_at ?? Math.floor(Date.now() / 1000) + 3000) * 1000,
    }
  }
  return {
    ...(includeContentType ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function authenticatedFetch(
  path: string,
  init: RequestInit = {},
  includeContentType = true
): Promise<Response> {
  const headers = await getAuthHeaders(includeContentType)
  let response = await fetch(`${API_BASE}${path}`, { ...init, headers })

  if (response.status === 401) {
    const refreshedHeaders = await getAuthHeaders(includeContentType, true)
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: refreshedHeaders,
    })
  }
  return response
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `API error ${response.status}`
    const rawBody = await response.text()
    try {
      const errorData = JSON.parse(rawBody)
      if (errorData.detail) {
        errorMessage = typeof errorData.detail === "string"
          ? errorData.detail
          : JSON.stringify(errorData.detail)
      }
    } catch {
      if (rawBody) errorMessage += `: ${rawBody}`
    }
    throw new Error(errorMessage)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const api = {
  async get<T>(path: string): Promise<T> {
    const response = await authenticatedFetch(path)
    return handleResponse<T>(response)
  },

  async post<T>(path: string, body?: unknown): Promise<T> {
    const response = await authenticatedFetch(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    })
    return handleResponse<T>(response)
  },

  async put<T>(path: string, body?: unknown): Promise<T> {
    const response = await authenticatedFetch(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    })
    return handleResponse<T>(response)
  },

  async delete<T>(path: string): Promise<T> {
    const response = await authenticatedFetch(path, {
      method: "DELETE",
    })
    return handleResponse<T>(response)
  },

  async upload<T>(path: string, body: FormData): Promise<T> {
    const response = await authenticatedFetch(path, {
      method: "POST",
      body,
    }, false)
    return handleResponse<T>(response)
  },
}
