import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, download } from '../api.js'
import JobSteps from '../components/JobSteps.jsx'
import Regenerate from '../components/Regenerate.jsx'
import { ErrorCard } from '../components/SetupCard.jsx'
import { money0, niceDate, pct0 } from '../format.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'

const STEPS = ['Upload', 'Match columns', 'Match categories', 'Check and score']

function Stepper({ step }) {
  return (
    <ol className="stepper" aria-label="Import steps">
      {STEPS.map((s, i) => (
        <li key={s} className={i === step ? 'on' : i < step ? 'done' : ''} aria-current={i === step ? 'step' : undefined}>
          <span className="n" aria-hidden="true">{i < step ? <Icon.check /> : i + 1}</span>{s}
        </li>
      ))}
    </ol>
  )
}

function UploadStep({ onUploaded, storeSlug }) {
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const pick = async (files) => {
    const f = files?.[0]
    if (!f) return
    setErr(null); setBusy(true)
    try { onUploaded(await api.importUpload(f)) } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <label htmlFor="imp-file" onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files) }}
        style={{ position: 'relative', border: `2px dashed ${drag ? 'var(--green)' : 'var(--sage)'}`, background: drag ? 'var(--green-tint)' : '#FFFFFF', borderRadius: 26, padding: '40px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center', cursor: 'pointer' }}>
        <span style={{ width: 64, height: 64, borderRadius: 20, background: 'var(--green-tint)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} aria-hidden="true">{busy ? <Icon.spinner /> : <Icon.upload />}</span>
        <span className="head" style={{ fontWeight: 700, fontSize: 22 }}>{busy ? 'Reading your file…' : 'Drop your sales file here'}</span>
        <span style={{ fontSize: 15, color: 'var(--muted)', maxWidth: 460 }}>
          A CSV or Excel (.xlsx) export from your till, POS or online shop: one row per item or order, with who bought, when and how much they paid.
        </span>
        <span className="btn ink" aria-hidden="true">Choose file</span>
        <input id="imp-file" type="file" accept=".csv,.txt,.xlsx,.xlsm" onChange={(e) => pick(e.target.files)} style={{ position: 'absolute', width: 1, height: 1, opacity: 0 }} />
      </label>
      {err && <div className="notice tomato" role="alert">{err}</div>}
      <div className="notice green" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Icon.info />
        <span style={{ flex: '1 1 300px' }}>Not sure what to export? Start from the template: customer ID, date, product, category, quantity and amount paid.</span>
        <button type="button" className="btn outline" onClick={async () => download('dimaagi-cart-template.csv', await api.template(), 'text/csv')}>
          <Icon.download />Download template
        </button>
      </div>
      {storeSlug && <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>This month's file will update your store “{storeSlug}”; its column and category matches are reused.</p>}
      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>Your file stays on this computer. Nothing is uploaded to the internet.</p>
    </div>
  )
}

function ColumnsStep({ up, mapping, setMapping }) {
  const opts = ['', ...up.columns]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--line)', fontWeight: 700 }}>First rows of {up.filename}</div>
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl"><thead><tr>{up.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
            <tbody>{up.preview.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </div>
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <h2 className="h2 sm">Which column is which?</h2>
        <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>Dimaagi Cart guessed from the column names. Customer, date and amount are required; category makes the basket signals (staples, fresh produce) work.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
          {up.fields.map((f) => (
            <label key={f.key} className="field" htmlFor={`map-${f.key}`}>
              <span>{f.label} {f.required ? <span style={{ color: 'var(--tomato-text)' }}>(required)</span> : f.key === 'category' ? <span className="muted">(strongly recommended)</span> : <span className="muted">(optional)</span>}</span>
              <select id={`map-${f.key}`} value={mapping[f.key] || ''} onChange={(e) => setMapping({ ...mapping, [f.key]: e.target.value || null })}>
                {opts.map((c) => <option key={c} value={c}>{c || '— not in my file —'}</option>)}
              </select>
              {up.suggested[f.key] && mapping[f.key] === up.suggested[f.key] && <span style={{ fontSize: 12, color: 'var(--green)', fontWeight: 600 }}>Suggested</span>}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}

function CategoriesStep({ up, cats, categoryMap, setCategoryMap }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h2 className="h2 sm">Match your categories to the model's departments</h2>
      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>
        The model looks at how much of each customer's spend goes to grocery, fresh produce, meat, deli and so on, and whether they still buy
        staples (milk, bread, cheese, cereal, eggs). Suggestions come from your category names; change any that are wrong. They're saved for next month.
      </p>
      <table className="tbl">
        <thead><tr><th scope="col">Your category</th><th scope="col">Share of sales</th><th scope="col">Counts as</th></tr></thead>
        <tbody>
          {cats.map((c, i) => (
            <tr key={c.name}>
              <th scope="row" style={{ fontWeight: 600 }}>{c.name}</th>
              <td className="num">{pct0(c.share_of_sales)}</td>
              <td>
                <label className="sr-only" htmlFor={`cat-${i}`}>Department for {c.name}</label>
                <select id={`cat-${i}`} className="select-sm" value={categoryMap[c.name] || c.target} onChange={(e) => setCategoryMap({ ...categoryMap, [c.name]: e.target.value })}>
                  {up.targets.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
                {(categoryMap[c.name] || c.target) === 'OTHER' && <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--tomato-text)' }}>not used</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Report({ r }) {
  const dropped = Object.entries(r.dropped || {})
  const items = [
    ['Customers', r.customers.toLocaleString('en-US')], ['Regular customers (5+ trips)', r.regular_customers.toLocaleString('en-US')],
    ['Date range', `${niceDate(r.from)} – ${niceDate(r.to)}`], ['History', `${r.weeks} weeks (${r.days} days)`],
    ['Trips', r.trips.toLocaleString('en-US')], ['Sales', money0(r.sales)],
  ]
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h2 className="h2 sm">Data check</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
        {items.map(([k, v]) => (
          <div key={k} style={{ background: 'var(--cream)', borderRadius: 14, padding: '10px 12px' }}>
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>{k}</div><div style={{ fontWeight: 700, fontSize: 17 }}>{v}</div>
          </div>
        ))}
      </div>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, lineHeight: 1.6 }}>
        {dropped.length === 0 ? <li>No missing or unreadable values in the matched columns.</li> :
          dropped.map(([k, n]) => <li key={k}>{n.toLocaleString('en-US')} rows skipped: {k}.</li>)}
        {r.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
    </div>
  )
}

export default function Import() {
  const { health, jobs, track, busy, refresh } = useApp()
  const [params] = useSearchParams()
  const existing = (health?.app?.stores || []).filter((s) => !s.demo)
  const [step, setStep] = useState(0)
  const [up, setUp] = useState(null)
  const [mapping, setMapping] = useState({})
  const [categoryMap, setCategoryMap] = useState({})
  const [analysis, setAnalysis] = useState(null)
  const [store, setStore] = useState(params.get('store') || '')
  const [storeName, setStoreName] = useState('')
  const [mode, setMode] = useState('pretrained')
  const [err, setErr] = useState(null)
  const [working, setWorking] = useState(false)
  const [jobId, setJobId] = useState(null)
  const job = jobs.import?.id === jobId ? jobs.import : null      // only the import started on this visit

  useEffect(() => {
    const s = existing.find((x) => x.slug === store)
    if (s) setStoreName(s.name)
  }, [store]) // eslint-disable-line react-hooks/exhaustive-deps

  const analyze = async (next) => {
    setErr(null); setWorking(true)
    try {
      const a = await api.importAnalyze(up.import_id, { mapping, category_map: categoryMap, store: store || null })
      setAnalysis(a)
      setStep(next)
    } catch (e) { setErr(e.message) }
    setWorking(false)
  }
  const run = async () => {
    setErr(null)
    try {
      const started = await api.importRun(up.import_id, { mapping, category_map: categoryMap, store: store || null, store_name: storeName.trim(), mode })
      setJobId(started.id)
      track(started)
    } catch (e) { setErr(e.message) }
  }
  useEffect(() => { if (job?.status === 'done') refresh() }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const r = analysis?.report
  const required = up?.fields.filter((f) => f.required).every((f) => mapping[f.key])
  const done = job?.status === 'done'

  return (
    <div className="page" style={{ gap: 22 }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="eyebrow">Bring your own data</span>
        <h1 className="h1">Connect your sales data</h1>
        <p className="lead">Four short steps. Dimaagi Cart converts your export into the shape the model understands, then scores every regular customer.</p>
      </header>
      <Stepper step={done ? 4 : step} />
      {err && <ErrorCard error={{ message: err }} />}

      {step === 0 && <UploadStep storeSlug={store} onUploaded={(u) => { setUp(u); setMapping(u.suggested); setStep(1) }} />}
      {step === 1 && up && <ColumnsStep up={up} mapping={mapping} setMapping={setMapping} />}
      {step === 2 && analysis && <CategoriesStep up={up} cats={analysis.categories} categoryMap={categoryMap} setCategoryMap={setCategoryMap} />}
      {step === 3 && r && (
        <>
          <Report r={r} />
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <h2 className="h2 sm">Score your customers</h2>
            <fieldset style={{ border: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }} disabled={!!job && job.status === 'running'}>
              <legend className="sr-only">How to score</legend>
              <label className={`choice ${mode === 'pretrained' ? 'on' : ''}`}>
                <input type="radio" name="mode" value="pretrained" checked={mode === 'pretrained'} onChange={() => setMode('pretrained')} disabled={!r.can_score} />
                <span><strong>Score with the pre-trained model</strong><br />
                  <span className="muted">Works with any amount of history. A behaviour-only model trained on a US grocery chain (2017): a starting point.</span></span>
              </label>
              <label className={`choice ${mode === 'train' ? 'on' : ''}`} aria-disabled={!r.can_train}>
                <input type="radio" name="mode" value="train" checked={mode === 'train'} onChange={() => setMode('train')} disabled={!r.can_train} />
                <span><strong>Train a model on your data</strong><br />
                  <span className="muted">
                    {r.can_train
                      ? 'Tested on your newest customers, then compared with the pre-trained behaviour-only model on the same test; Dimaagi Cart keeps the better one.'
                      : `Needs about ${r.min_training_days} days of history (8 months); your file has ${r.days}. Use the pre-trained model for now.`}
                  </span></span>
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, paddingTop: 6 }}>
                {existing.length > 0 && (
                  <label className="field" htmlFor="imp-store">Store
                    <select id="imp-store" value={store} onChange={(e) => { setStore(e.target.value); if (!e.target.value) setStoreName('') }}>
                      <option value="">A new store</option>
                      {existing.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
                    </select>
                  </label>
                )}
                <label className="field" htmlFor="imp-name">Store name
                  <input id="imp-name" value={storeName} onChange={(e) => setStoreName(e.target.value)} placeholder="e.g. Corner Market" readOnly={!!store} />
                </label>
              </div>
            </fieldset>
            {!r.can_score && <div className="notice tomato" role="alert">No customer has 5 or more trips yet, so there's nobody to score. Export a longer period.</div>}
            {!job || job.status !== 'running' ? (
              !done && <button type="button" className="btn tomato" style={{ alignSelf: 'flex-start' }} onClick={run} disabled={busy || !r.can_score || !storeName.trim()}>
                {mode === 'train' ? 'Train, compare and score' : 'Score my customers'}
              </button>
            ) : null}
            {job && <JobSteps job={job} steps={job.steps.map((s) => ({ key: s.key, label: s.label }))} />}
            {job?.status === 'error' && <div className="notice tomato" role="alert">{job.error}</div>}
          </div>
          {done && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }} role="status">
              <h2 className="h2 sm">Your customers are scored</h2>
              <p style={{ margin: 0, fontSize: 15 }}>
                {job.result.model === 'store' ? 'Your own model did better on your newest customers, so it is in use.' :
                  'Scored with the pre-trained model (trained on a US grocery chain): a starting point.'}
              </p>
              {job.result.small_segments?.length > 0 && (
                <div className="notice butter"><Icon.warning />Small segments: {job.result.small_segments.join(', ')} {job.result.small_segments.length > 1 ? 'have' : 'has'} fewer than 10 customers, so patterns there may be chance.</div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <Link className="btn tomato" to="/">See the dashboard</Link>
                  <Link className="btn outline" to="/customers">See customers</Link>
                </div>
                <Regenerate what="both" label="Write reasons and kits" />
              </div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>Reasons and campaign kits are written by Gemini from your segments: about two calls per segment on your key.</p>
            </div>
          )}
        </>
      )}

      {step > 0 && !done && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <button type="button" className="btn outline" onClick={() => setStep(step - 1)} disabled={working || job?.status === 'running'}>Back</button>
          {step === 1 && <button type="button" className="btn ink" onClick={() => analyze(2)} disabled={!required || working}>{working ? 'Checking…' : 'Next: categories'}</button>}
          {step === 2 && <button type="button" className="btn ink" onClick={() => analyze(3)} disabled={working}>{working ? 'Checking…' : 'Next: check my data'}</button>}
        </div>
      )}
    </div>
  )
}
