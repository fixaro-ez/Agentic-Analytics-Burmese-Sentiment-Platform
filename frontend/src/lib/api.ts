const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
type CachedAccessToken = { token: string; expiresAt: number }

let cachedAccessToken: CachedAccessToken | null = null
let sessionTokenPromise: Promise<string | null> | null = null
let refreshTokenPromise: Promise<string | null> | null = null

function cacheSessionToken(
  session: { access_token: string; expires_at?: number } | null
): string | null {
  if (!session?.access_token) {
    cachedAccessToken = null
    return null
  }
  cachedAccessToken = {
    token: session.access_token,
    expiresAt: (session.expires_at ?? Math.floor(Date.now() / 1000) + 3000) * 1000,
  }
  return session.access_token
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshTokenPromise) {
    refreshTokenPromise = (async () => {
      const { createClient } = await import("@/lib/supabase/client")
      const { data, error } = await createClient().auth.refreshSession()
      if (error) throw error
      return cacheSessionToken(data.session)
    })().finally(() => {
      refreshTokenPromise = null
    })
  }
  return refreshTokenPromise
}

async function getAccessToken(forceRefresh = false): Promise<string | null> {
  if (forceRefresh) {
    cachedAccessToken = null
    return refreshAccessToken()
  }

  if (
    cachedAccessToken &&
    cachedAccessToken.expiresAt > Date.now() + 60_000
  ) {
    return cachedAccessToken.token
  }

  if (!sessionTokenPromise) {
    sessionTokenPromise = (async () => {
      const { createClient } = await import("@/lib/supabase/client")
      const { data, error } = await createClient().auth.getSession()
      if (error) throw error
      const session = data.session
      if (session && (session.expires_at ?? 0) * 1000 <= Date.now() + 60_000) {
        return refreshAccessToken()
      }
      return cacheSessionToken(session)
    })().finally(() => {
      sessionTokenPromise = null
    })
  }
  return sessionTokenPromise
}

async function getAuthHeaders(
  includeContentType = true,
  refresh = false
): Promise<HeadersInit> {
  const token = await getAccessToken(refresh)
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
  const headers = new Headers(init.headers)
  const authHeaders = new Headers(await getAuthHeaders(includeContentType))
  authHeaders.forEach((value, key) => headers.set(key, value))
  let response = await fetch(`${API_BASE}${path}`, { ...init, headers })

  if (response.status === 401) {
    const refreshedHeaders = new Headers(init.headers)
    const refreshedAuthHeaders = new Headers(
      await getAuthHeaders(includeContentType, true)
    )
    refreshedAuthHeaders.forEach((value, key) =>
      refreshedHeaders.set(key, value)
    )
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

  async stream(path: string, body?: unknown): Promise<Response> {
    const response = await authenticatedFetch(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) {
      await handleResponse<never>(response)
    }
    return response
  },

  async openStream(path: string): Promise<Response> {
    const response = await authenticatedFetch(path, {
      method: "GET",
      headers: { Accept: "text/event-stream" },
    })
    if (!response.ok) {
      await handleResponse<never>(response)
    }
    return response
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
