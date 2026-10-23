import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { niceDate, pct0 } from '../format.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'
import { ErrorCard, Loading } from './SetupCard.jsx'

const CARD = { background: '#FFFFFF', border: '1px solid var(--border)', borderRadius: 22, padding: 24 }

export function CaptureBars({ capture, height = 150 }) {
  const groups = ['10%', '20%', '30%'].filter((k) => capture.model?.[k] !== undefined)
  const top = Math.max(0.6, ...groups.map((k) => capture.model[k]))
  const bar = (v, color) => ({ width: '100%', height: Math.round((v / top) * (height - 22)), borderRadius: '8px 8px 3px 3px', background: color })
  const label = groups.map((k) => `riskiest ${k} reaches ${pct0(capture.model[k])} (rule ${pct0(capture.recency_rule?.[k])}, random ${pct0(capture.random?.[k])})`).join('; ')
  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${groups.length}, minmax(0, 1fr))`, gap: 16, alignItems: 'end', height: height + 40 }}
        role="img" aria-label={`Contacting the ${label}`}>
        {groups.map((k) => (
          <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%', justifyContent: 'flex-end' }}>
            <div style={{ display: 'flex', gap: 5, alignItems: 'flex-end', height }}>
              {[['model', 'var(--green)', 700], ['recency_rule', 'var(--sage)', 400], ['random', 'var(--sand)', 400]].map(([key, color, w]) => (
                <div key={key} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 4, height: '100%' }}>
                  <span style={{ fontSize: 13, fontWeight: w, color: w === 700 ? 'var(--ink)' : 'var(--muted)' }}>{pct0(capture[key]?.[k])}</span>
                  <div style={bar(capture[key]?.[k] ?? 0, color)} />
                </div>
              ))}
            </div>
            <span style={{ textAlign: 'center', fontSize: 13, fontWeight: 600, color: 'var(--muted)' }}>Top {k}</span>
          </div>
        ))}
      </div>
      <div className="legend">
        <span><span className="swatch" style={{ background: 'var(--green)' }} />Dimaagi Cart model</span>
        <span><span className="swatch" style={{ background: 'var(--sage)' }} />Days-since-last-visit rule</span>
        <span><span className="swatch" style={{ background: 'var(--sand)' }} />Random</span>
      </div>
    </>
  )
}

function Fact({ k, v }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 600 }}>{k}</span>
      <span style={{ fontSize: 15, lineHeight: 1.45 }}>{v}</span>
    </div>
  )
}

function Comparison({ c }) {
  const rows = [['Trained on your data', c.store_model, c.kept === 'store'],
    ['Pre-trained behaviour-only model (US grocery chain, 2017)', c.pretrained_model, c.kept === 'pretrained']]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>Champion vs challenger</h3>
      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>
        Both models were scored on the same {c.test_customers?.toLocaleString('en-US')} customers from your newest period
        (from {niceDate(c.test_period_from)}). Dimaagi Cart keeps the one with the higher ROC-AUC.
      </p>
      <table className="tbl">
        <thead><tr><th scope="col">Model</th><th scope="col">ROC-AUC</th><th scope="col">Reach at 20%</th><th scope="col"><span className="sr-only">Kept</span></th></tr></thead>
        <tbody>
          {rows.map(([name, m, kept]) => (
            <tr key={name}>
              <th scope="row" style={{ fontWeight: 600 }}>{name}</th>
              <td className="num">{m?.roc_auc ?? '—'}</td>
              <td className="num">{m?.capture?.['20%'] !== undefined ? pct0(m.capture['20%']) : '—'}</td>
              <td>{kept && <span className="chip ok"><Icon.check />In use</span>}</td>
            </tr>
          ))}
          <tr><th scope="row" style={{ fontWeight: 600 }}>Days-since-last-visit rule</th><td className="num">{c.recency_rule_roc_auc}</td><td>—</td><td /></tr>
        </tbody>
      </table>
    </div>
  )
}

// Both shipped models, scored on the same newest period of the demo data
function PretrainedModels({ models }) {
  const rows = ['full', 'behaviour'].map((k) => models[k]).filter(Boolean)
  if (!rows.length) return null
  const t = rows[0]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>The pre-trained models</h3>
      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>
        Both trained on the demo data and tested on the same {t.test_customers?.toLocaleString('en-US')} customers from its newest
        period{t.cutoffs?.length ? ` (from ${niceDate(t.cutoffs[t.cutoffs.length - 1])})` : ''}. Imported stores start with the
        behaviour-only model, because they have no campaign, coupon or discount data.
      </p>
      <table className="tbl">
        <thead><tr><th scope="col">Model</th><th scope="col">ROC-AUC</th><th scope="col">PR-AUC</th><th scope="col">Reach at 10 / 20 / 30%</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row" style={{ fontWeight: 600 }}>{r.label}</th>
              <td className="num">{r.roc_auc}</td>
              <td className="num">{r.pr_auc}</td>
              <td className="num">{r.capture ? ['10%', '20%', '30%'].map((k) => pct0(r.capture[k])).join(' / ') : '—'}</td>
            </tr>
          ))}
          <tr><th scope="row" style={{ fontWeight: 600 }}>Days-since-last-visit rule</th><td className="num">{t.recency_rule_roc_auc}</td><td>—</td><td>—</td></tr>
        </tbody>
      </table>
    </div>
  )
}

// Everything about the model in use for the active store, from models/metrics.json
export default function ModelCard() {
  const { version } = useApp()
  const [m, setM] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.model().then(setM, setError) }, [version])
  if (error) return error.code === 'missing_output' ? null : <ErrorCard error={error} />
  if (!m) return <Loading label="Loading the model card" />
  const t = m.trained_on
  const gain = m.roc_auc != null && m.recency_rule_roc_auc != null ? m.roc_auc - m.recency_rule_roc_auc : null
  return (
    <section style={{ ...CARD, display: 'flex', flexDirection: 'column', gap: 20 }} aria-labelledby="model-card-h">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <h2 id="model-card-h" className="h2 sm">Model card</h2>
        <span className={`chip ${m.source === 'pretrained' ? 'butter' : 'ok'}`}>
          {m.source === 'pretrained' ? 'Pre-trained behaviour-only model: a starting point' : m.store.demo ? 'Demo store model' : 'Trained on your data'}
        </span>
      </div>
      {m.source === 'pretrained' && !m.store.demo && (
        <div className="notice butter"><Icon.info />Scored with the pre-trained model (trained on a US grocery chain): a starting point. Train on your own data once you have about 8 months of history.</div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        <Fact k="What it predicts" v="Silent churn: a regular customer's weekly spend dropping by half or more in the next 61 days" />
        <Fact k="Trained on" v={t ? `${niceDate(t.from)} – ${niceDate(t.to)} · ${t.households?.toLocaleString('en-US')} households` : 'Not recorded (retrain to record it)'} />
        {m.store_data && <Fact k="Your data" v={`${niceDate(m.store_data.from)} – ${niceDate(m.store_data.to)} · ${m.store_data.households?.toLocaleString('en-US')} customers`} />}
        <Fact k="How it was tested" v={`${m.validation}${m.cutoffs?.length ? ` Test period from ${niceDate(m.cutoffs[m.cutoffs.length - 1])}${m.test_customers ? `, ${m.test_customers.toLocaleString('en-US')} customers` : ''}.` : ''}`} />
        <Fact k="Model" v={`XGBoost (gradient-boosted trees), ${m.n_features} behaviour signals${m.trained_at ? `, trained ${niceDate(m.trained_at)}` : ''}`} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        {[['ROC-AUC', m.roc_auc], ['Recency rule', m.recency_rule_roc_auc], ['Better by', gain != null ? `${gain >= 0 ? '+' : ''}${gain.toFixed(3)}` : '—'], ['PR-AUC', m.pr_auc]].map(([k, v]) => (
          <div key={k} style={{ background: 'var(--cream)', borderRadius: 16, padding: '12px 14px' }}>
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>{k}</div>
            <div className="head num" style={{ fontWeight: 700, fontSize: 26 }}>{v ?? '—'}</div>
          </div>
        ))}
      </div>
      {m.capture && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>How many drifters you'll reach</h3>
          <CaptureBars capture={m.capture} height={130} />
        </div>
      )}
      {m.comparison && <Comparison c={m.comparison} />}
      {m.pretrained_models && <PretrainedModels models={m.pretrained_models} />}
      <details className="how">
        <summary>Features used ({m.n_features})</summary>
        {m.behaviour_only && <p style={{ fontSize: 14, color: 'var(--muted)', margin: '10px 0 0' }}>Behaviour-only model: campaign, coupon and discount signals are left out, because this store has no such data.</p>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, paddingTop: 12 }}>
          {m.features.map((g) => (
            <div key={g.group}>
              <h4 style={{ margin: '0 0 6px', fontSize: 14 }}>{g.group}</h4>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, lineHeight: 1.6 }}>
                {g.features.map((f) => (
                  <li key={f.feature} style={f.unavailable ? { color: 'var(--muted)', textDecoration: 'line-through' } : undefined}>
                    {f.label}{f.unavailable && <span className="sr-only"> (unavailable)</span>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </details>
      <div>
        <h3 style={{ margin: '0 0 6px', fontSize: 17, fontWeight: 700 }}>Limitations</h3>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, lineHeight: 1.6, color: 'var(--body)' }}>
          {m.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </div>
    </section>
  )
}
