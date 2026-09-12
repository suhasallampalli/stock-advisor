// Thin typed client over the stock-advisor FastAPI backend. Same-origin in
// production (served by that same app); proxied in dev (see vite.config.ts).

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface UserOut {
  id: string
  email: string
  full_name: string | null
  auth_provider: string
  is_active: boolean
  is_verified: boolean
  created_at: string
}

export interface HoldingOut {
  symbol: string
  quantity: number
  avg_price: number
  last_price: number
  pnl: number
  pnl_pct: number
  broker: string
}

export interface PortfolioOut {
  total_invested: number
  total_value: number
  unrealised_pnl: number
  unrealised_pnl_pct: number
  realised_pnl: number
  holdings: HoldingOut[]
  errors: string[]
}

export interface BrokerCredOut {
  broker: string
  fields_set: string[]
  masked: Record<string, string>
  updated_at: string
}

export interface BriefOut {
  session: string
  horizon: string
  emailed: boolean
  text: string
  html: string
}

export type BrokerName = 'zerodha' | 'upstox' | 'angelone'
export type Session = 'premarket' | 'market_open' | 'postmarket'

const ACCESS_KEY = 'advisor.access_token'
const REFRESH_KEY = 'advisor.refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function setTokens(pair: Pick<TokenPair, 'access_token' | 'refresh_token'>) {
  localStorage.setItem(ACCESS_KEY, pair.access_token)
  localStorage.setItem(REFRESH_KEY, pair.refresh_token)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export function isLoggedIn(): boolean {
  return !!getAccessToken()
}

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let refreshing: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return false
  const resp = await fetch('/auth/refresh', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!resp.ok) return false
  const pair: TokenPair = await resp.json()
  setTokens(pair)
  return true
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { auth = true, retry = true }: { auth?: boolean; retry?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  if (auth) {
    const token = getAccessToken()
    if (token) headers.set('authorization', `Bearer ${token}`)
  }
  if (init.body && !(init.body instanceof URLSearchParams) && !headers.has('content-type')) {
    headers.set('content-type', 'application/json')
  }

  const resp = await fetch(path, { ...init, headers })

  if (resp.status === 401 && auth && retry) {
    if (!refreshing) refreshing = tryRefresh().finally(() => (refreshing = null))
    const ok = await refreshing
    if (ok) return request<T>(path, init, { auth, retry: false })
    clearTokens()
    window.location.href = '/login'
    throw new ApiError(401, 'Session expired')
  }

  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      /* not JSON */
    }
    throw new ApiError(resp.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }

  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}

export const api = {
  register: (email: string, password: string) =>
    request<TokenPair>('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }, { auth: false }),

  login: (email: string, password: string) =>
    request<TokenPair>(
      '/auth/login',
      { method: 'POST', body: new URLSearchParams({ username: email, password }) },
      { auth: false },
    ),

  googleAuthorize: () => request<{ authorization_url: string }>('/auth/google/authorize', {}, { auth: false }),

  me: () => request<UserOut>('/auth/me'),

  logout: () => {
    const refresh_token = localStorage.getItem(REFRESH_KEY)
    if (!refresh_token) return Promise.resolve()
    return request<void>('/auth/logout', { method: 'POST', body: JSON.stringify({ refresh_token }) })
  },

  logoutAll: () => request<void>('/auth/logout-all', { method: 'POST' }),

  listBrokers: () => request<BrokerCredOut[]>('/brokers'),

  upsertBroker: (broker: BrokerName, fields: Record<string, string>) =>
    request<BrokerCredOut>(`/brokers/${broker}`, { method: 'PUT', body: JSON.stringify({ fields }) }),

  deleteBroker: (broker: BrokerName) => request<void>(`/brokers/${broker}`, { method: 'DELETE' }),

  portfolio: () => request<PortfolioOut>('/me/portfolio'),

  brief: (session: Session, sendEmail: boolean) =>
    request<BriefOut>(`/me/brief?session=${session}&send_email=${sendEmail}`, { method: 'POST' }),
}

export { ApiError }
