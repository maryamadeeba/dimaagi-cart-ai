import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, pickFolder } from '../api.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'
import JobSteps from './JobSteps.jsx'

const KBS = {
  reviews: {
    title: 'Grocery reviews knowledge base',
    what: 'Why shoppers leave, in their own words. Point Dimaagi Cart at the folder holding the Yelp Open Dataset files ' +
      '(yelp_academic_dataset_business.json and yelp_academic_dataset_review.json). Reviews stay on this computer.',
    steps: [{ key: 'check', label: 'Find the Yelp files' }, { key: 'ingest', label: 'Pick grocery reviews and tag them' },
      { key: 'embed', label: 'Embed reviews on this computer', hint: 'Takes a while the first time' },
      { key: 'bm25', label: 'Build the keyword index' }],
  },
  trends: {
    title: 'Marketing trends knowledge base',
    what: 'What tactics work. Point Dimaagi Cart at the folder of report PDFs listed in config/trend_sources.csv.',
    steps: [{ key: 'check', label: 'Find the report PDFs' }, { key: 'index', label: 'Chunk, embed and index the reports' }],
  },
}

function KbRow({ kind, built }) {
  const { jobs, track, busy } = useApp()
  const [path, setPath] = useState('')
  const [err, setErr] = useState(null)
  const job = jobs[`build-${kind}`]
  const kb = KBS[kind]
  const start = async () => {
    setErr(null)
    try { track(await api.buildKb(kind, path.trim())) } catch (e) { setErr(e.message) }
  }
  const browse = async () => {
    const p = await pickFolder?.()
    if (p) setPath(p)
  }
  const id = `kb-${kind}`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 14, borderTop: '1px solid var(--line)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>{kb.title}</h3>
        {built ? <span className="chip ok"><Icon.check />Built</span> : <span className="chip butter">Not built yet</span>}
      </div>
      {!built && <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>{kb.what}</p>}
      {!built && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label className="field" htmlFor={id} style={{ flex: '1 1 260px' }}>Folder
            <input id={id} value={path} onChange={(e) => setPath(e.target.value)} placeholder={'C:\\path\\to\\folder'}
              autoComplete="off" spellCheck="false" />
          </label>
          {pickFolder && <button type="button" className="btn outline" onClick={browse}>Browse…</button>}
          <button type="button" className="btn ink" onClick={start} disabled={!path.trim() || busy}>Build</button>
        </div>
      )}
      {err && <div className="notice tomato" role="alert">{err}</div>}
      {job && <JobSteps job={job} steps={kb.steps} />}
      {job?.status === 'error' && <div className="notice tomato" role="alert">{job.error}</div>}
    </div>
  )
}

// Friendly first-run card: shown instead of a broken page when outputs or knowledge bases are missing.
export default function SetupCard({ title = 'Finish setting up Dimaagi Cart', message, showKbs = true }) {
  const { health } = useApp()
  const kb = health?.kb || {}
  return (
    <section className="card" aria-label="Setup" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
        <span className="step-n ai" style={{ width: 40, height: 40, borderRadius: 12 }} aria-hidden="true"><Icon.retrain /></span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <h2 className="h2 sm">{title}</h2>
          {message && <p style={{ margin: 0, fontSize: 15, color: 'var(--body)', lineHeight: 1.55 }}>{message}</p>}
        </div>
      </div>
      {showKbs && <KbRow kind="reviews" built={kb.reviews} />}
      {showKbs && <KbRow kind="trends" built={kb.trends} />}
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap',
        paddingTop: 14, borderTop: '1px solid var(--line)' }}>
        <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>Gemini API key</h3>
        {health?.has_key ? <span className="chip ok"><Icon.check />Saved</span> :
          <Link className="btn outline" to="/retrain#ai-settings">Add your key</Link>}
      </div>
    </section>
  )
}

export function ErrorCard({ error }) {
  return (
    <div className="notice tomato" role="alert">
      <Icon.warning color="#B5441D" />
      <span>{error?.message || 'Something went wrong.'}</span>
    </div>
  )
}

export function Loading({ label = 'Loading' }) {
  return <div className="skeleton" role="status" aria-label={label} />
}
