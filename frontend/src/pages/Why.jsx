import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import HowMade from '../components/HowMade.jsx'
import Regenerate from '../components/Regenerate.jsx'
import SegmentTabs from '../components/SegmentTabs.jsx'
import SetupCard, { ErrorCard, Loading } from '../components/SetupCard.jsx'
import { money0, orderSegments, shortName } from '../format.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'


function Reason({ r }) {
  return (
    <article className="card r20" style={{ padding: 22, display: 'flex', gap: 18 }}>
      <span className="head" aria-hidden="true" style={{ flexShrink: 0, width: 40, height: 40, borderRadius: 12, background: 'var(--ink)', color: 'var(--cream)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 18 }}>{r.n}</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}><span className="sr-only">Reason {r.n}: </span>{r.title}</h3>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: 'var(--body)' }}>{r.text}</p>
        {r.refs.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, paddingTop: 2 }} aria-label="Backed by reviews">
            {r.refs.map((ref) => <span key={ref} className="chip sm warn">{ref}</span>)}
          </div>
        )}
      </div>
    </article>
  )
}

function Review({ v }) {
  const n = Math.round(v.stars || 0)
  const [more, setMore] = useState(false)
  const full = `${v.text}${v.truncated ? '…' : ''}`
  const hasMore = v.short !== v.text
  return (
    <figure style={{ margin: 0, padding: 16, borderRadius: 16, background: 'var(--cream)', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="chip sm warn">{v.ref}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--tomato-text)' }} role="img" aria-label={`${n} out of 5 stars`}>{'★'.repeat(n)}<span style={{ color: 'var(--sand)' }}>{'★'.repeat(5 - n)}</span></span>
      </div>
      <blockquote id={`q-${v.ref}`} style={{ margin: 0, fontSize: 15, lineHeight: 1.5 }}>“{more || !hasMore ? full : v.short}”</blockquote>
      {hasMore && (
        <button type="button" className="linkish" aria-expanded={more} aria-controls={`q-${v.ref}`} onClick={() => setMore(!more)}
          style={{ alignSelf: 'flex-start', fontSize: 13 }}>{more ? 'Show less' : 'Show more'}</button>
      )}
      <figcaption style={{ fontSize: 12, color: 'var(--muted)' }}>Yelp review · another store{v.topic ? ` · ${v.topic}` : ''}</figcaption>
    </figure>
  )
}

export default function Why() {
  const { dashboard, dashError, version } = useApp()
  const { slug } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const segs = dashboard ? orderSegments(dashboard.segments, dashboard.focus) : []
  const current = slug || dashboard?.focus

  useEffect(() => {
    if (!current) return
    let live = true
    setData(null); setError(null)
    api.reasons(current).then((d) => live && setData(d), (e) => live && setError(e))
    return () => { live = false }
  }, [current, version])

  const head = (
    <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className="eyebrow">Why they leave</span>
      <h1 className="h1">What's pushing each group away</h1>
      <p className="lead">Likely reasons, each backed by real grocery reviews. Where the evidence is thin, Dimaagi Cart says so instead of guessing.</p>
    </header>
  )
  if (dashError) {
    return <div className="page">{head}{dashError.code === 'missing_output' ? <SetupCard message={dashError.message} /> : <ErrorCard error={dashError} />}</div>
  }

  return (
    <div className="page">
      {head}
      {segs.length > 0 && <SegmentTabs segments={segs} value={current} onChange={(s) => navigate(`/why/${s}`, { replace: true })} panelId="why-panel" />}
      <div id="why-panel" role="tabpanel" aria-labelledby={current ? `tab-${current}` : undefined} style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div className="notice green">
          <Icon.info />
          <span>Reviews come from shoppers at <strong>other grocery stores</strong>, a stand-in for your customers' voice. They're matched by product and theme, never to a real customer.</span>
        </div>
        {error?.code === 'missing_output' ? (
          <>
            <SetupCard title="Write the reasons" message={error.message} />
            {current && <Regenerate what="reasons" label="Write reasons for all segments" />}
          </>
        ) :
          error ? <ErrorCard error={error} /> : !data ? <Loading /> : (
            <section style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>
              <div className="col-main">
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 10 }}>
                    <h2 className="h2">{shortName(data.name)}</h2>
                    <span style={{ fontSize: 15, color: 'var(--muted)' }}>{data.customers} customers · {money0(data.weekly_revenue_at_risk)} / week at risk</span>
                  </div>
                  <Regenerate slug={current} what="reasons" label="Regenerate reasons" segmentName={shortName(data.name)} />
                </div>
                {data.too_small && <div className="notice butter"><Icon.warning />Only {data.customers} customers: treat these reasons as a hint, not a finding.</div>}
                {data.reasons.map((r) => <Reason key={r.n} r={r} />)}
                <div className="notice butter" style={{ borderRadius: 20, padding: '20px 22px', gap: 14 }}>
                  <Icon.warning />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: 15 }}>Evidence gaps</span>
                    <span style={{ fontSize: 15, lineHeight: 1.55 }}>{data.gaps}</span>
                  </div>
                </div>
                <HowMade how={data.how} kind="reasons" />
              </div>
              <aside aria-label="Reviews behind these reasons" className="card" style={{ flex: '1 1 320px', minWidth: 0, padding: 22, display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>Reviews behind these reasons</h2>
                  <span style={{ fontSize: 13, color: 'var(--muted)' }}>1–3 stars</span>
                </div>
                {data.reviews.map((v) => <Review key={v.ref} v={v} />)}
              </aside>
            </section>
          )}
      </div>
      <div className="dark" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 16, borderRadius: 22, padding: '22px 26px' }}>
        <span style={{ fontSize: 17, fontWeight: 600 }}>Ready to act on this? The campaign kit turns these reasons into an offer, email, SMS and post.</span>
        <Link className="btn tomato" to={current ? `/win-back/${current}` : '/win-back'}>Open the campaign kit</Link>
      </div>
    </div>
  )
}
