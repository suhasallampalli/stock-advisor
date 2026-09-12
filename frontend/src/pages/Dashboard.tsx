import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import BriefPanel from '../components/BriefPanel'
import BrokerCard from '../components/BrokerCard'
import Portfolio from '../components/Portfolio'
import { useAuth } from '../auth/AuthContext'

type Tab = 'portfolio' | 'brokers' | 'brief' | 'account'

const TABS: { value: Tab; label: string }[] = [
  { value: 'portfolio', label: 'Portfolio' },
  { value: 'brokers', label: 'Brokers' },
  { value: 'brief', label: 'Brief' },
  { value: 'account', label: 'Account' },
]

export default function Dashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('portfolio')

  const doLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div>
      <div className="topbar">
        <h1>stock-advisor</h1>
        <div className="muted">{user?.email}</div>
      </div>
      <p className="muted" style={{ marginTop: -6 }}>
        Automated rule-based output plus AI commentary for your personal review. Not investment advice.
      </p>

      <div className="tabs">
        {TABS.map((t) => (
          <div key={t.value} className={`tab ${tab === t.value ? 'active' : ''}`} onClick={() => setTab(t.value)}>
            {t.label}
          </div>
        ))}
      </div>

      {tab === 'portfolio' && <Portfolio />}
      {tab === 'brokers' && <BrokerCard />}
      {tab === 'brief' && <BriefPanel />}
      {tab === 'account' && (
        <div className="panel">
          <p>
            <b>Email:</b> {user?.email}
          </p>
          <p>
            <b>Sign-in method:</b> {user?.auth_provider}
          </p>
          <p>
            <b>Joined:</b> {user ? new Date(user.created_at).toLocaleDateString() : ''}
          </p>
          <button className="btn" onClick={doLogout}>
            Log out
          </button>
        </div>
      )}
    </div>
  )
}
