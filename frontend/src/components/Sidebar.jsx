import { NavLink, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { Icon, LogoMark } from '../icons.jsx'
import { niceDate } from '../format.js'
import { useApp } from '../state.jsx'

const LINKS = [
  { to: '/', label: 'Dashboard', icon: Icon.dashboard, end: true },
  { to: '/customers', label: 'Customers', icon: Icon.users },
  { to: '/why', label: 'Why they leave', icon: Icon.search },
  { to: '/win-back', label: 'Win them back', icon: Icon.message },
  { to: '/ask', label: 'Ask Dimaagi', icon: Icon.star },
  { to: '/retrain', label: 'Retrain', icon: Icon.retrain },
]
const IMPORT = '__import__'

function StoreSwitcher() {
  const { health, refresh, busy, newChat } = useApp()
  const navigate = useNavigate()
  const list = health?.app?.stores || []
  const active = health?.app?.active_store
  const change = async (slug) => {
    if (slug === IMPORT) { navigate('/import'); return }
    await api.activateStore(slug)
    newChat()                      // the chat's sources belong to the previous store
    await refresh()
    navigate('/')
  }
  if (!list.length) return null
  return (
    <label className="switcher" htmlFor="store-switch">
      <span>Store</span>
      <select id="store-switch" value={active} onChange={(e) => change(e.target.value)} disabled={busy}>
        {list.map((s) => <option key={s.slug} value={s.slug}>{s.demo ? 'Demo store (dunnhumby)' : s.name}</option>)}
        <option value={IMPORT}>+ Import another store…</option>
      </select>
    </label>
  )
}

export default function Sidebar() {
  const { dashboard, health } = useApp()
  const trained = dashboard?.model?.trained_at
  return (
    <nav className="nav" aria-label="Main">
      <div className="brand"><LogoMark /><span>Dimaagi Cart</span></div>
      {LINKS.map(({ to, label, icon: I, end }) => (
        <NavLink key={to} to={to} end={end}><I />{label}</NavLink>
      ))}
      <div className="store">
        <strong>{dashboard?.store_name || health?.app?.store?.name || '[STORE NAME]'}</strong>
        {dashboard?.as_of && <div>Data through {niceDate(dashboard.as_of)}</div>}
        {trained && <div>Model trained {niceDate(trained)}</div>}
        {dashboard?.model?.source === 'pretrained' && <div>Pre-trained model</div>}
        {health?.version && <div>Dimaagi Cart v{health.version}</div>}
        <NavLink to="/about" className="about-link">About and credits</NavLink>
        <StoreSwitcher />
      </div>
    </nav>
  )
}
