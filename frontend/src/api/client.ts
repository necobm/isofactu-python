/** Minimal typed HTTP client for the backend API. */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  /** Sent as JSON, except `FormData` (file uploads), which goes as multipart/form-data. */
  body?: unknown
  query?: object
  signal?: AbortSignal
}

type UnauthorizedListener = () => void
const unauthorizedListeners = new Set<UnauthorizedListener>()

/**
 * Registers a callback run whenever the API answers `401` (no / expired session, paused
 * account...). The auth provider uses it to drop the current user and show the login page.
 * Returns the function that unregisters the listener.
 */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  for (const [key, value] of Object.entries(options.query ?? {}) as [string, unknown][]) {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value))
  }

  const isForm = options.body instanceof FormData
  const response = await fetch(url, {
    method: options.method ?? 'GET',
    headers: {
      Accept: 'application/json',
      // Multipart bodies get their Content-Type (with the boundary) from the browser
      ...(options.body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
    },
    body: options.body === undefined ? undefined : isForm ? (options.body as FormData) : JSON.stringify(options.body),
    signal: options.signal,
    // The session travels in an HttpOnly cookie (also when the API lives on another origin)
    credentials: 'include',
  })

  if (response.status === 204) return undefined as T

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const payload = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const detail = isJson && payload && typeof payload === 'object' ? payload.detail : payload
    if (response.status === 401) unauthorizedListeners.forEach((listener) => listener())
    throw new ApiError(response.status, detail, describeError(response.status, detail))
  }
  return payload as T
}

function describeError(status: number, detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (e && typeof e === 'object' && 'msg' in e ? String(e.msg) : JSON.stringify(e)))
      .join('; ')
  }
  return `Error ${status}`
}
