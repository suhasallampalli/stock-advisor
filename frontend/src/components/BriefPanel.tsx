import { useState } from 'react'
import { api, ApiError, type BriefOut, type Session } from '../api'

const SESSIONS: { value: Session; label: string }[] = [
  { value: 'premarket', label: 'Pre-open (08:45 IST) — calls for today' },
  { value: 'market_open', label: 'Market-open (09:25 IST) — indices + F&O gap scan' },
  { value: 'postmarket', label: 'Post-close (15:45 IST) — calls for tomorrow' },
]

export default function BriefPanel() {
  const [session, setSession] = useState<Session>('market_open')
  const [brief, setBrief] = useState<BriefOut | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  const run = async (sendEmail: boolean) => {
    setError('')
    setBusy(true)
    setSent(false)
    try {
      const result = await api.brief(session, sendEmail)
      setBrief(result)
      setSent(sendEmail && result.emailed)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to build brief')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <label htmlFor="session">Session</label>
      <select id="session" value={session} onChange={(e) => setSession(e.target.value as Session)} style={{ maxWidth: 420 }}>
        {SESSIONS.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>

      <div style={{ marginTop: 14, display: 'flex', gap: 8 }}>
        <button className="btn" onClick={() => run(false)} disabled={busy}>
          {busy ? 'Building…' : 'Preview'}
        </button>
        <button className="btn primary" onClick={() => run(true)} disabled={busy}>
          Email it to me
        </button>
      </div>

      {error && <div className="error" style={{ marginTop: 10 }}>{error}</div>}
      {sent && <div className="card">Sent — check your inbox.</div>}

      {brief && (
        <iframe
          className="brief-frame"
          style={{ marginTop: 16 }}
          sandbox=""
          srcDoc={brief.html}
          title={`${brief.session} brief`}
        />
      )}
    </div>
  )
}
