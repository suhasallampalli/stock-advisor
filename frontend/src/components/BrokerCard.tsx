import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type BrokerCredOut, type BrokerName } from '../api'

// Mirrors BROKER_FIELDS in src/advisor/api/routers/brokers.py — keep in sync.
const BROKER_FIELDS: Record<BrokerName, { key: string; label: string; secret?: boolean; required?: boolean }[]> = {
  zerodha: [
    { key: 'api_key', label: 'API key', required: true },
    { key: 'api_secret', label: 'API secret', secret: true, required: true },
    { key: 'access_token', label: "Today's access token" },
  ],
  upstox: [
    { key: 'api_key', label: 'API key', required: true },
    { key: 'api_secret', label: 'API secret', secret: true, required: true },
    { key: 'redirect_uri', label: 'Redirect URI' },
    { key: 'access_token', label: "Today's access token" },
  ],
  angelone: [
    { key: 'api_key', label: 'API key', required: true },
    { key: 'client_id', label: 'Client ID', required: true },
    { key: 'mpin', label: 'MPIN', secret: true, required: true },
    { key: 'totp_secret', label: 'TOTP secret', secret: true, required: true },
  ],
}

const LABELS: Record<BrokerName, string> = {
  zerodha: 'Zerodha (Kite Connect)',
  upstox: 'Upstox',
  angelone: 'Angel One (SmartAPI)',
}

function BrokerForm({ broker, existing, onSaved }: {
  broker: BrokerName
  existing?: BrokerCredOut
  onSaved: () => void
}) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api.upsertBroker(broker, values)
      setValues({})
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await api.deleteBroker(broker)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={save} style={{ maxWidth: 420 }}>
      {BROKER_FIELDS[broker].map((f) => (
        <div key={f.key}>
          <label htmlFor={`${broker}-${f.key}`}>
            {f.label}
            {existing?.fields_set.includes(f.key) && (
              <span className="muted"> — currently {existing.masked[f.key] || 'set'}</span>
            )}
          </label>
          <input
            id={`${broker}-${f.key}`}
            type={f.secret ? 'password' : 'text'}
            placeholder={existing?.fields_set.includes(f.key) ? 'leave blank to keep current' : ''}
            required={f.required && !existing}
            value={values[f.key] ?? ''}
            onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
          />
        </div>
      ))}
      {error && <div className="error">{error}</div>}
      <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
        <button className="btn primary" type="submit" disabled={busy}>
          {existing ? 'Update' : 'Connect'}
        </button>
        {existing && (
          <button className="btn danger" type="button" onClick={remove} disabled={busy}>
            Remove
          </button>
        )}
      </div>
    </form>
  )
}

export default function BrokerCard() {
  const [brokers, setBrokers] = useState<BrokerCredOut[] | null>(null)
  const [open, setOpen] = useState<BrokerName | null>(null)
  const [error, setError] = useState('')

  const load = () => {
    api.listBrokers().then(setBrokers).catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load brokers'))
  }

  useEffect(load, [])

  if (error) return <div className="error">{error}</div>
  if (!brokers) return <div className="muted">Loading brokers…</div>

  const byName = Object.fromEntries(brokers.map((b) => [b.broker, b])) as Record<string, BrokerCredOut>

  return (
    <div>
      {(Object.keys(LABELS) as BrokerName[]).map((broker) => {
        const existing = byName[broker]
        return (
          <div key={broker} className="panel">
            <div className="topbar">
              <div>
                <b>{LABELS[broker]}</b>{' '}
                {existing ? <span className="muted">connected</span> : <span className="muted">not connected</span>}
              </div>
              <button className="btn" onClick={() => setOpen(open === broker ? null : broker)}>
                {open === broker ? 'Close' : existing ? 'Edit' : 'Connect'}
              </button>
            </div>
            {open === broker && (
              <BrokerForm
                broker={broker}
                existing={existing}
                onSaved={() => {
                  load()
                  setOpen(null)
                }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
