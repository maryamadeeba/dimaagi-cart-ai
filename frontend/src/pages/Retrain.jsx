import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import DataFolder from '../components/DataFolder.jsx'
import { api } from '../api.js'
import JobSteps from '../components/JobSteps.jsx'
import ModelCard from '../components/ModelCard.jsx'
import SetupCard from '../components/SetupCard.jsx'
import { niceDate, pct0 } from '../format.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'

const STEPS = [
  { key: 'check', label: 'Check the file', hint: 'Columns, dates, missing values and how much history you have' },
  { key: 'convert', label: 'Match columns and categories', hint: 'Your categories mapped to the departments the model knows' },
  { key: 'train', label: 'Score, or retrain and test on the newest weeks', hint: 'Your own model is kept only if it beats the pre-trained one on the same test' },
  { key: 'segments', label: 'Refresh segments', hint: "Who's drifting, and what they cut back on" },
  { key: 'reasons', label: 'Rewrite reasons and campaign kits', hint: 'Uses your Gemini key, a few calls per run' },
]
const MODELS = {
  gemini_model: [['gemini-3.8-flash', 'best quality'], ['gemini-3.5-flash-lite', 'faster']],
  chat_model: [['gemini-3.5-flash-lite', 'fast'], ['gemini-3.8-flash', 'more thorough']],
}

function Upload() {
  const { health } = useApp()
  const own = health?.app?.store && !health.app.store.demo ? health.app.active_store : null
  return (
    <div className="col-main" style={{ gap: 20 }}>
      <Link to={own ? `/import?store=${encodeURIComponent(own)}` : '/import'} className="dropzone">
        <span style={{ width: 64, height: 64, borderRadius: 20, background: 'var(--green-tint)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} aria-hidden="true"><Icon.upload /></span>
        <span className="head" style={{ fontWeight: 700, fontSize: 22, color: 'var(--ink)' }}>{own ? "Load this month's sales file" : 'Connect your sales data'}</span>
        <span style={{ fontSize: 15, color: 'var(--muted)', maxWidth: 440 }}>
          A CSV or Excel export from your till or POS: one row per item sold, with customer, date, product and price.
          {own ? ' Your column and category matches are reused.' : ' The demo store stays as it is.'}
        </span>
        <span className="btn ink">{own ? 'Open the import' : 'Start the import'}</span>
      </Link>
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <h2 className="h2 sm">What happens next</h2>
        <JobSteps job={null} steps={STEPS} aiKeys={['reasons']} />
      </div>
    </div>
  )
}

function StartScreen() {
  const { refresh } = useApp()
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h2 className="h2 sm">Start screen</h2>
      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>Choose between your own data and the demo store again. Nothing is deleted.</p>
      <button type="button" className="btn outline" onClick={async () => { await api.showWelcome(); refresh() }}>Show the welcome screen</button>
      <Link to="/about" style={{ fontSize: 14 }}>About Dimaagi Cart, data sources and credits</Link>
    </div>
  )
}

function CurrentModel() {
  const { dashboard } = useApp()
  const m = dashboard?.model
  const reach = m?.capture?.model?.['20%']
  const gain = m && m.roc_auc - m.recency_rule_roc_auc
  return (
    <div className="dark" style={{ borderRadius: 26, padding: 26, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="head" style={{ margin: 0, fontWeight: 700, fontSize: 21 }}>Current model</h2>
        <span className="chip" style={{ background: m ? 'var(--green-tint)' : 'var(--butter)', color: m ? 'var(--green)' : 'var(--ink)', fontWeight: 700 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: m ? 'var(--green)' : 'var(--tomato)' }} />{m ? 'Ready' : 'Not trained'}
        </span>
      </div>
      {m && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
            {[['ROC-AUC', m.roc_auc], ['Reach at 20%', reach !== undefined ? pct0(reach) : '—'], ['Signals', m.n_features],
              ['Beats recency rule', gain !== undefined ? `${gain >= 0 ? '+' : ''}${gain.toFixed(2)}` : '—']].map(([k, v]) => (
              <div key={k} style={{ background: 'rgba(251,247,239,0.08)', borderRadius: 16, padding: 14 }}>
                <div style={{ fontSize: 13, color: 'var(--on-dark)' }}>{k}</div>
                <div className="head num" style={{ fontWeight: 700, fontSize: 28 }}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--on-dark)' }}>
            {dashboard.as_of && <>Data through {niceDate(dashboard.as_of)} · </>}
            {m.cutoffs?.length > 0 && <>tested on customers from {niceDate(m.cutoffs[m.cutoffs.length - 1])} · </>}
            {m.trained_at && <>trained {niceDate(m.trained_at)}</>}
          </div>
        </>
      )}
    </div>
  )
}

const KEY_SOURCES = {
  credential_manager: 'Saved in the app (Windows Credential Manager)',
  folder_env: "From this data folder's .env file",
  environment: 'From an environment variable set outside the app',
}

function KeyStatus({ source }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 14 }} role="status">
      <span className={`chip ${source ? 'ok' : 'butter'}`}>{source ? <><Icon.check />Key found</> : 'No key yet'}</span>
      <span className="muted">{source ? KEY_SOURCES[source] : 'Paste one below to write reasons, kits and chat answers.'}</span>
    </div>
  )
}

function AiSettings() {
  const { refresh } = useApp()
  const [s, setS] = useState(null)
  const [key, setKey] = useState('')
  const [msg, setMsg] = useState(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => { api.settings().then(setS, (e) => setMsg({ err: true, text: e.message })) }, [])
  const save = async (values) => {
    setSaving(true); setMsg(null)
    try {
      setS(await api.saveSettings(values))
      setKey('')
      setMsg({ text: 'Settings saved.' })
      refresh()
    } catch (e) { setMsg({ err: true, text: e.message }) }
    setSaving(false)
  }
  const options = (field) => {
    const list = [...MODELS[field]]
    if (s && !list.some(([v]) => v === s[field])) list.unshift([s[field], 'current'])
    return list.map(([v, note]) => <option key={v} value={v}>{v} ({note})</option>)
  }
  return (
    <form id="ai-settings" className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14, scrollMarginTop: 24 }}
      onSubmit={(e) => { e.preventDefault(); save({ gemini_key: key || null, gemini_model: s?.gemini_model, chat_model: s?.chat_model }) }}>
      <h2 className="h2 sm">AI settings</h2>
      <label className="field" htmlFor="key">Gemini API key
        <input id="key" type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" spellCheck="false"
          placeholder={s?.has_key ? 'Saved. Paste a new key to replace it' : 'Paste your key'} />
      </label>
      {s && <KeyStatus source={s.key_source} />}
      <label className="field" htmlFor="model">Writing model
        <select id="model" value={s?.gemini_model || ''} onChange={(e) => setS({ ...s, gemini_model: e.target.value })} disabled={!s}>{s && options('gemini_model')}</select>
      </label>
      <label className="field" htmlFor="chat-model">Chat model
        <select id="chat-model" value={s?.chat_model || ''} onChange={(e) => setS({ ...s, chat_model: e.target.value })} disabled={!s}>{s && options('chat_model')}</select>
      </label>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13, lineHeight: 1.5, color: 'var(--muted)' }}>
        <Icon.lock />
        <span>Your key is kept in Windows Credential Manager, and your sales data stays on this computer. Only short review snippets and segment numbers are sent to Gemini.</span>
      </div>
      <button type="submit" className="btn tomato" disabled={saving || !s}>Save settings</button>
      {s?.has_key && <button type="button" className="btn outline" onClick={() => save({ clear_key: true })} disabled={saving}>Remove saved key</button>}
      {msg && <div className={`notice ${msg.err ? 'tomato' : 'green'}`} role={msg.err ? 'alert' : 'status'}>{msg.text}</div>}
    </form>
  )
}

export default function Retrain() {
  const { health } = useApp()
  const { hash } = useLocation()
  useEffect(() => {
    if (hash === '#ai-settings') document.getElementById('ai-settings')?.scrollIntoView({ block: 'start' })
  }, [hash])
  const kbReady = health?.kb?.reviews && health?.kb?.trends
  return (
    <div className="page" style={{ gap: 22 }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="eyebrow">Retrain</span>
        <h1 className="h1">Bring in this month's sales</h1>
        <p className="lead" style={{ maxWidth: 660 }}>Load new transactions once a month. Dimaagi Cart retrains, tests itself on the newest weeks, and refreshes who's drifting.</p>
        {health?.app?.active_store === 'demo' && <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>You're looking at the demo store, which is never changed. Importing creates your own store.</p>}
      </header>
      <section style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'stretch' }}>
        <Upload />
        <div className="col-side" style={{ gap: 20 }}>
          <CurrentModel />
          <AiSettings />
          <DataFolder />
          <StartScreen />
        </div>
      </section>
      <ModelCard />
      {health && !kbReady && <SetupCard title="Knowledge bases" message="Reasons and campaign kits are written from two knowledge bases built on this computer. They are never shipped with the app." />}
    </div>
  )
}
