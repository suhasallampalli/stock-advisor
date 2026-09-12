import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setTokens } from '../api'
import { useAuth } from '../auth/AuthContext'

// Google auth completes on the backend (/auth/google/callback), which 302s
// the browser here with tokens in the URL *fragment* (never sent to a
// server): #access_token=...&refresh_token=...&expires_in=...
export default function OAuthCallback() {
  const navigate = useNavigate()
  const { refreshUser } = useAuth()
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1))
    const access_token = params.get('access_token')
    const refresh_token = params.get('refresh_token')
    if (!access_token || !refresh_token) {
      setError('Sign-in did not return tokens. Please try again.')
      return
    }
    setTokens({ access_token, refresh_token })
    // Drop the tokens from the URL/history before navigating on.
    window.history.replaceState(null, '', '/oauth-callback')
    refreshUser().then(() => navigate('/dashboard', { replace: true }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (error) {
    return (
      <div className="center-page">
        <div className="panel">
          <div className="error">{error}</div>
        </div>
      </div>
    )
  }
  return <div className="center-page muted">Signing you in…</div>
}
