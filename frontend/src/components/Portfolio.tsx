import { useEffect, useState } from 'react'
import { api, ApiError, type PortfolioOut } from '../api'

const inr = (n: number) => `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

export default function Portfolio() {
  const [p, setP] = useState<PortfolioOut | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.portfolio().then(setP).catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load portfolio'))
  }, [])

  if (error) return <div className="error">{error} — connect a broker first.</div>
  if (!p) return <div className="muted">Loading portfolio…</div>

  return (
    <div>
      <div className="card">
        <b>Portfolio</b>
        <br />
        Invested {inr(p.total_invested)} &middot; Value {inr(p.total_value)} &middot; Unrealised{' '}
        <span className={p.unrealised_pnl >= 0 ? 'pos' : 'neg'}>
          {p.unrealised_pnl >= 0 ? '+' : ''}
          {inr(p.unrealised_pnl)} ({p.unrealised_pnl_pct.toFixed(1)}%)
        </span>
        {p.realised_pnl !== 0 && <> &middot; Realised (all-time) {inr(p.realised_pnl)}</>}
        {p.errors.length > 0 && (
          <div className="error" style={{ marginTop: 6 }}>
            data warnings: {p.errors.join('; ')}
          </div>
        )}
      </div>

      {p.holdings.length === 0 ? (
        <p className="muted">No holdings yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Stock</th>
              <th>Qty</th>
              <th>Avg</th>
              <th>Last</th>
              <th>P&amp;L%</th>
              <th>Broker</th>
            </tr>
          </thead>
          <tbody>
            {p.holdings.map((h) => (
              <tr key={`${h.broker}-${h.symbol}`}>
                <td>{h.symbol}</td>
                <td>{h.quantity}</td>
                <td>₹{h.avg_price.toFixed(1)}</td>
                <td>₹{h.last_price.toFixed(1)}</td>
                <td className={h.pnl_pct >= 0 ? 'pos' : 'neg'}>
                  {h.pnl_pct >= 0 ? '+' : ''}
                  {h.pnl_pct.toFixed(1)}%
                </td>
                <td>{h.broker}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
