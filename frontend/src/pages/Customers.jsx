import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import SetupCard, { ErrorCard, Loading } from '../components/SetupCard.jsx'
import { money2, orderSegments, pct0, shortName } from '../format.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'

const COLUMNS = [
  { key: 'id', label: 'Customer ID' }, { key: 'risk', label: 'Risk' }, { key: 'segment', label: 'Segment' },
  { key: 'spend', label: 'Weekly spend' }, { key: 'revenue', label: 'Revenue at risk' }, { key: null, label: 'Top reason' },
]
const PAGE_SIZE = 25

function RiskBar({ risk }) {
  const color = risk >= 0.7 ? 'var(--tomato)' : risk >= 0.4 ? 'var(--butter)' : 'var(--sage)'
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span className="num" style={{ fontWeight: 700, minWidth: 38 }}>{pct0(risk)}</span>
      <span className="bar-track" style={{ width: 60, height: 8 }} aria-hidden="true"><span style={{ display: 'block', width: pct0(risk), height: '100%', background: color, borderRadius: 999 }} /></span>
    </span>
  )
}

function Drawer({ id, onClose }) {
  const [c, setC] = useState(null)
  const [error, setError] = useState(null)
  const closeRef = useRef(null)
  useEffect(() => {
    setC(null); setError(null)
    api.customer(id).then(setC, setError)
    closeRef.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [id, onClose])
  const max = c ? Math.max(...c.drivers.map((d) => Math.abs(d.shap)), 0.01) : 1
  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-h">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <h2 id="drawer-h" className="h2 sm">Customer {id}</h2>
          <button ref={closeRef} type="button" className="btn outline" onClick={onClose} aria-label="Close customer details" style={{ padding: '0 14px' }}><Icon.cross /></button>
        </div>
        {error && <ErrorCard error={error} />}
        {!c && !error && <Loading />}
        {c && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
              {[['Risk of drifting', pct0(c.risk)], ['Segment', c.at_risk ? shortName(c.segment) : 'Healthy'],
                ['Usual weekly spend', money2(c.spend_per_week)], ['Last visit', `${c.recency_days} days ago`]].map(([k, v]) => (
                <div key={k} style={{ background: 'var(--cream)', borderRadius: 14, padding: '10px 12px' }}>
                  <div style={{ fontSize: 13, color: 'var(--muted)' }}>{k}</div>
                  <div style={{ fontWeight: 700, fontSize: 17 }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>Why the model scored them this way</h3>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>The three signals that moved this customer's risk most (SHAP values).</p>
            </div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
              {c.drivers.map((d) => {
                const up = d.shap > 0
                return (
                  <li key={d.feature} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span style={{ fontSize: 15, fontWeight: 600 }}>{d.phrase}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span className="bar-track" style={{ flex: 1, height: 12 }} aria-hidden="true">
                        <span style={{ display: 'block', height: '100%', width: `${(Math.abs(d.shap) / max) * 100}%`, borderRadius: 999, background: up ? 'var(--tomato)' : 'var(--green)' }} />
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 700, color: up ? 'var(--tomato-text)' : 'var(--green)', minWidth: 92 }}>{up ? 'Raises risk' : 'Lowers risk'}</span>
                    </span>
                  </li>
                )
              })}
            </ul>
            {c.at_risk && c.segment_slug ? (
              <div className="dark" style={{ borderRadius: 18, padding: 18, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <span style={{ fontWeight: 700 }}>What to send</span>
                <span style={{ fontSize: 14, color: 'var(--on-dark)' }}>They're in the {shortName(c.segment)} group. Its campaign kit has the offer, email, SMS and the fixes to make first.</span>
                <Link className="btn tomato" to={`/win-back/${c.segment_slug}`} style={{ alignSelf: 'flex-start' }}>Open their campaign kit</Link>
              </div>
            ) : (
              <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>Not in the riskiest 20%, so no campaign is suggested.</p>
            )}
          </>
        )}
      </aside>
    </>
  )
}

export default function Customers() {
  const { dashboard, version } = useApp()
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState({ key: 'risk', desc: true })
  const [segment, setSegment] = useState('')
  const [atRisk, setAtRisk] = useState(false)
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(null)
  const close = useCallback(() => setOpen(null), [])

  useEffect(() => { const t = setTimeout(() => { setQuery(q); setPage(1) }, 250); return () => clearTimeout(t) }, [q])
  useEffect(() => {
    let live = true
    api.customers({ q: query, sort: sort.key, desc: sort.desc, page, page_size: PAGE_SIZE, segment, at_risk: atRisk })
      .then((d) => live && (setData(d), setError(null)), (e) => live && setError(e))
    return () => { live = false }
  }, [query, sort, page, segment, atRisk, version])

  const head = (
    <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className="eyebrow">Customers</span>
      <h1 className="h1">Every regular, scored</h1>
      <p className="lead">The model's risk score for each regular shopper (5+ trips), and the signals behind it. Click a customer to see why.</p>
    </header>
  )
  if (error?.code === 'missing_output') return <div className="page">{head}<SetupCard title="No customers yet" message={error.message} showKbs={false} /></div>
  const segs = dashboard ? orderSegments(dashboard.segments, dashboard.focus) : []
  const toggleSort = (key) => { setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== 'id' && key !== 'segment' })); setPage(1) }

  return (
    <div className="page" style={{ gap: 20 }}>
      {head}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
        <label className="field" htmlFor="cust-q" style={{ flex: '1 1 260px' }}>Search
          <input id="cust-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Customer ID or reason, e.g. staples" />
        </label>
        <label className="field" htmlFor="cust-seg" style={{ flex: '0 1 240px' }}>Segment
          <select id="cust-seg" value={segment} onChange={(e) => { setSegment(e.target.value); setPage(1) }}>
            <option value="">All customers</option>
            {segs.map((s) => <option key={s.slug} value={s.slug}>{shortName(s.name)}</option>)}
          </select>
        </label>
        <label className="check" style={{ minHeight: 44, alignItems: 'center' }}>
          <input type="checkbox" checked={atRisk} onChange={(e) => { setAtRisk(e.target.checked); setPage(1) }} style={{ marginTop: 0 }} />
          <span>At-risk only</span>
        </label>
      </div>
      {error && <ErrorCard error={error} />}
      {!data ? <Loading /> : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl rows" aria-label="Scored customers" aria-rowcount={data.total}>
              <thead>
                <tr>
                  {COLUMNS.map((col) => (
                    <th key={col.label} scope="col" aria-sort={col.key && sort.key === col.key ? (sort.desc ? 'descending' : 'ascending') : undefined}>
                      {col.key ? (
                        <button type="button" className="sort" onClick={() => toggleSort(col.key)}>
                          {col.label}{sort.key === col.key ? (sort.desc ? ' ↓' : ' ↑') : ''}
                        </button>
                      ) : col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.id} onClick={() => setOpen(r.id)} className={open === r.id ? 'selected' : undefined}>
                    <th scope="row">
                      <button type="button" className="linkish" onClick={(e) => { e.stopPropagation(); setOpen(r.id) }}>{r.id}</button>
                    </th>
                    <td><RiskBar risk={r.risk} /></td>
                    <td>{r.at_risk ? shortName(r.segment) : <span className="muted">Healthy</span>}</td>
                    <td className="num">{money2(r.spend_per_week)}</td>
                    <td className="num">{r.at_risk ? money2(r.revenue_at_risk) : <span className="muted">—</span>}</td>
                    <td style={{ minWidth: 220 }}>{r.top_reason || <span className="muted">—</span>}</td>
                  </tr>
                ))}
                {data.rows.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 24 }}>No customers match.</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '12px 18px', borderTop: '1px solid var(--line)', fontSize: 14 }}>
            <span className="muted" role="status">
              {data.total.toLocaleString('en-US')} of {data.all.toLocaleString('en-US')} regular customers · {data.at_risk.toLocaleString('en-US')} at risk
            </span>
            <nav aria-label="Pages" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button type="button" className="btn outline" disabled={data.page <= 1} onClick={() => setPage(data.page - 1)}>Previous</button>
              <span>Page {data.page} of {data.pages}</span>
              <button type="button" className="btn outline" disabled={data.page >= data.pages} onClick={() => setPage(data.page + 1)}>Next</button>
            </nav>
          </div>
        </div>
      )}
      {open && <Drawer id={open} onClose={close} />}
    </div>
  )
}
