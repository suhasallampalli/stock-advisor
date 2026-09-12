import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../auth/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  const withGoogle = async () => {
    setError('')
    try {
      const { authorization_url } = await api.googleAuthorize()
      window.location.href = authorization_url
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Google sign-in is not configured')
    }
  }

  return (
    <div className="center-page">
      <div className="panel" style={{ width: 360 }}>
        <h2>Log in</h2>
        <p className="muted" style={{ marginTop: 0 }}>stock-advisor</p>
        <form onSubmit={submit}>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="error">{error}</div>}
          <button className="btn primary" type="submit" disabled={busy} style={{ marginTop: 16, width: '100%' }}>
            {busy ? 'Logging in…' : 'Log in'}
          </button>
        </form>
        <button className="btn" onClick={withGoogle} style={{ marginTop: 10, width: '100%' }}>
          Continue with Google
        </button>
        <p className="muted" style={{ marginTop: 16 }}>
          No account? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  )
}
