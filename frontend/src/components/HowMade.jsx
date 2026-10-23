import { niceDate } from '../format.js'
import { Icon } from '../icons.jsx'
import { RefChip } from './RichText.jsx'

const TOOL_NAMES = {
  list_segments: 'List segments', get_segment_reasons: 'Segment reasons', search_reviews: 'Search reviews',
  search_marketing_trends: 'Search marketing reports', get_campaign_kit: 'Get campaign kit',
}

function Row({ k, children }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 170px) 1fr', gap: 12, fontSize: 14, lineHeight: 1.5 }}>
      <span style={{ color: 'var(--muted)', fontWeight: 600 }}>{k}</span>
      <div style={{ minWidth: 0 }}>{children}</div>
    </div>
  )
}

function Checks({ checks }) {
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {checks.map((c) => (
        <li key={c.name} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
          <span style={{ color: c.ok ? 'var(--green)' : 'var(--tomato-text)', flexShrink: 0 }} aria-hidden="true">{c.ok ? <Icon.check /> : <Icon.cross />}</span>
          <span><strong>{c.name}</strong><span className="sr-only">{c.ok ? ' passed' : ' needs a look'}</span>{c.detail ? `: ${c.detail}` : ''}</span>
        </li>
      ))}
    </ul>
  )
}

function stamp(at) {
  if (!at) return null
  const t = new Date(at)
  return `${niceDate(at)} ${t.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`
}

// Collapsible provenance for an AI output: which model, which retrieval, which searches, what came back, what was checked.
// kind: 'reasons' | 'kit' | 'chat'
export default function HowMade({ how, kind, compact }) {
  if (!how) return null
  const queries = kind === 'chat' ? how.tool_calls || [] : how.queries || []
  return (
    <details className={compact ? 'how compact' : 'how'}>
      <summary>How this was made</summary>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 12 }}>
        {kind !== 'chat' && !how.recorded && (
          <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>
            The model and searches weren't recorded for this run (it was written before the app existed). Regenerate to record them.
          </p>
        )}
        {how.stale && (
          <div className="notice butter" style={{ padding: '10px 14px' }}><Icon.warning />Written before your latest import: numbers may be out of date. Regenerate to refresh.</div>
        )}
        <Row k="AI model">{how.model || 'not recorded'} <span className="muted">(Google Gemini{kind === 'chat' ? ', picks which tools to call' : ''})</span></Row>
        <Row k="Retrieval">
          {kind === 'kit' ? 'Vector search over marketing reports; reviews come from the reasons analysis' :
            how.retrieval === 'hybrid_rerank' ? 'Hybrid search (vector + keyword, fused) then a local reranker' :
              how.retrieval === 'hybrid' ? 'Hybrid search (vector + keyword, fused)' : how.retrieval || 'not recorded'}
          {how.retrieval && <span className="muted"> · <code>{how.retrieval}</code></span>}
        </Row>
        {kind === 'reasons' && how.theme && <Row k="Segment theme">{how.theme}</Row>}
        {queries.length > 0 && (
          <Row k={kind === 'chat' ? 'Tool calls' : 'Searches run'}>
            <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 2 }}>
              {queries.map((q, i) => (
                <li key={i}>
                  {kind === 'chat' ? (
                    <><strong>{TOOL_NAMES[q.tool] || q.tool}</strong>{Object.values(q.args || {}).length > 0 && <>: “{Object.values(q.args).join(', ')}”</>}</>
                  ) : typeof q === 'string' ? `“${q}”` : <><span className="muted">{q.label}:</span> “{q.query}”</>}
                </li>
              ))}
            </ol>
          </Row>
        )}
        {kind === 'reasons' && (
          <Row k="Retrieved">{how.retrieved} reviews from other grocery stores; {how.cited} cited (shown as R1–R{how.cited}).
            {how.retrieved_refs?.length > 0 && <div className="muted" style={{ fontSize: 13 }}>Retrieved as {how.retrieved_refs.join(', ')} in models/why_summaries.md</div>}
          </Row>
        )}
        {kind === 'kit' && (
          <Row k="Retrieved">
            {how.retrieved} report pages, {how.reviews_used} reviews from the reasons
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 }}>
              {(how.retrieved_refs || []).map((r) => (
                <span key={r.ref} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}><RefChip id={r.ref} />{r.label}</span>
              ))}
            </div>
          </Row>
        )}
        {kind === 'chat' && (
          <Row k="Sources returned">
            {how.retrieved?.length ? (
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {how.retrieved.map((r) => (
                  <span key={r.ref} className="wrap-anywhere" style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                    <RefChip id={r.ref} /><span className="wrap-anywhere">{r.label}{r.file && <span className="muted"> · <code>{r.file}</code></span>}</span>
                  </span>
                ))}
              </span>
            ) : 'none new this turn'}
          </Row>
        )}
        {how.checks && <Row k="Code checks"><Checks checks={how.checks} /></Row>}
        {kind === 'chat' ? (
          how.model_seconds != null && <Row k="Time">{how.model_seconds}s model, {how.tool_seconds}s tools</Row>
        ) : (
          <Row k="Generated">{stamp(how.generated_at) || 'not recorded'}{how.from_cache ? ' (reused a saved answer)' : ''}</Row>
        )}
      </div>
    </details>
  )
}
