import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { api, clearTokens, isLoggedIn, setTokens, type UserOut } from '../api'

interface AuthState {
  user: UserOut | null
  loading: boolean
  loggedIn: boolean
  refreshUser: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = async () => {
    if (!isLoggedIn()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      setUser(await api.me())
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshUser()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = async (email: string, password: string) => {
    setTokens(await api.login(email, password))
    await refreshUser()
  }

  const register = async (email: string, password: string) => {
    setTokens(await api.register(email, password))
    await refreshUser()
  }

  const logout = async () => {
    try {
      await api.logout()
    } finally {
      clearTokens()
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, loggedIn: !!user, refreshUser, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth() must be used inside <AuthProvider>')
  return ctx
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { loading, loggedIn } = useAuth()
  if (loading) return <div className="center-page muted">Loading…</div>
  if (!loggedIn) return <Navigate to="/login" replace />
  return <>{children}</>
}
