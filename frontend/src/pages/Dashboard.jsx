import { Link } from 'react-router-dom'
import { CaptureBars } from '../components/ModelCard.jsx'
import SetupCard, { ErrorCard, Loading } from '../components/SetupCard.jsx'
import { cap, money0, money2, orderSegments, pct0, pct1, shortName } from '../format.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'

const CARD = { background: '#FFFFFF', border: '1px solid var(--border)' }
const KPI_NUM = { fontFamily: 'var(--head)', fontWeight: 700, fontSize: 44, letterSpacing: '-0.03em' }

function Kpi({ label, value, note, color }) {
  return (
    <div style={{ ...CARD, borderRadius: 20, padding: 22, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--muted)' }}>{label}</span>
      <span className="num" style={{ ...KPI_NUM, color }}>{value}</span>
      <span style={{ fontSize: 14, color: 'var(--muted)' }}>{note}</span>
    </div>
  )
}

// Tag chip and bar colour for each card, as in the design: highest value, largest group, fewer trips
function segmentLook(s, focus, largest) {
  if (s.slug === focus) return { tag: 'Highest value', cls: 'warn', bar: 'var(--tomato)' }
  if (s.slug === largest) return { tag: 'Largest group', cls: 'ok', bar: 'var(--green)' }
  return s.main_reason === 'visiting less'
    ? { tag: 'Fewer trips', style: { background: 'var(--line)', color: 'var(--ink)' }, bar: 'var(--sage)' }
    : { tag: 'Basket changed', style: { background: 'var(--line)', color: 'var(--ink)' }, bar: 'var(--sage)' }
}

function SegmentCard({ s, look }) {
  return (
    <article style={{ ...CARD, borderRadius: 22, padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <h3 className="head" style={{ margin: 0, fontWeight: 700, fontSize: 21, letterSpacing: '-0.01em' }}>{shortName(s.name)}</h3>
          <span style={{ fontSize: 14, color: 'var(--muted)' }}>{s.customers} customers · {s.main_reason}</span>
        </div>
        <span className={`chip ${look.cls || ''}`} style={look.style}>{look.tag}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span className="head num" style={{ fontWeight: 700, fontSize: 34, letterSpacing: '-0.02em' }}>{money0(s.weekly_revenue_at_risk)}</span>
        <span style={{ fontSize: 14, color: 'var(--muted)' }}>/ week at risk</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="bar-track"><div style={{ width: pct1(s.share_of_revenue_at_risk), background: look.bar }} /></div>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          {pct1(s.share_of_revenue_at_risk)} of revenue at risk · {money2(s.revenue_at_risk_per_customer)} per customer
        </span>
      </div>
      {s.lapsed_categories.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--muted)' }}>Cut back most on</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {s.lapsed_categories.map((c) => <span key={c} className="chip butter">{cap(c)}</span>)}
          </div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 16, paddingTop: 4, borderTop: '1px solid var(--line)', fontSize: 15, fontWeight: 600 }}>
        <Link to={`/why/${s.slug}`} style={{ paddingTop: 12, minHeight: 44 }} aria-label={`Why ${shortName(s.name)} customers leave`}>Why →</Link>
        <Link to={`/win-back/${s.slug}`} style={{ paddingTop: 12, minHeight: 44 }} aria-label={`Campaign for ${shortName(s.name)}`}>Campaign →</Link>
      </div>
    </article>
  )
}

function ReasonSplit({ split }) {
  const basket = split['basket changed'] || 0
  const visiting = split['visiting less'] || 0
  return (
    <div style={{ ...CARD, borderRadius: 22, padding: 26, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h2 className="head" style={{ margin: 0, fontWeight: 700, fontSize: 22 }}>
          {basket >= visiting ? 'Churn starts in the basket' : 'Churn starts with fewer visits'}
        </h2>
        <p style={{ margin: 0, fontSize: 15, color: 'var(--muted)', lineHeight: 1.5 }}>
          Share of at-risk customers by main reason. {basket >= visiting ? 'Most drifting customers still visit; they quietly stop buying staples here.'
            : 'Most drifting customers are coming in less often.'}
        </p>
      </div>
      <div style={{ display: 'flex', height: 54, borderRadius: 14, overflow: 'hidden' }} role="img"
        aria-label={`Share of at-risk customers by main reason: ${pct1(basket)} basket changed, ${pct1(visiting)} visiting less`}>
        <div style={{ width: pct1(basket), background: 'var(--green)', color: '#FFFFFF', display: 'flex', alignItems: 'center', paddingLeft: 16, fontWeight: 700, fontSize: 18 }}>{pct1(basket)}</div>
        <div style={{ width: pct1(visiting), background: 'var(--tomato)', color: '#FFFFFF', display: 'flex', alignItems: 'center', paddingLeft: 16, fontWeight: 700, fontSize: 18 }}>{pct1(visiting)}</div>
      </div>
      <div className="legend">
        <span><span className="swatch" style={{ background: 'var(--green)' }} />Basket changed: fewer staples, less produce</span>
        <span><span className="swatch" style={{ background: 'var(--tomato)' }} />Visiting less often</span>
      </div>
    </div>
  )
}

function CaptureChart({ capture }) {
  return (
    <div style={{ ...CARD, borderRadius: 22, padding: 26, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h2 className="head" style={{ margin: 0, fontWeight: 700, fontSize: 22 }}>How many drifters you'll reach</h2>
        <p style={{ margin: 0, fontSize: 15, color: 'var(--muted)', lineHeight: 1.5 }}>
          Share of drifting customers found, by how many customers you contact. Tested on a future period. <Link to="/model">About this model</Link>
        </p>
      </div>
      <CaptureBars capture={capture} />
    </div>
  )
}

export default function Dashboard() {
  const { dashboard: d, dashError } = useApp()
  if (dashError?.code === 'missing_output') {
    return (
      <div className="page">
        <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span className="eyebrow">Welcome to Dimaagi Cart</span>
          <h1 className="h1 big">Let's find the regulars who are drifting away.</h1>
        </header>
        <SetupCard title="Load your sales data" message={<>{dashError.message} <Link to="/retrain">Go to Retrain</Link>.</>} />
      </div>
    )
  }
  if (dashError) return <div className="page"><ErrorCard error={dashError} /></div>
  if (!d) return <div className="page"><Loading /></div>

  const segs = orderSegments(d.segments, d.focus)
  const focus = d.segments.find((s) => s.slug === d.focus)
  const largest = [...d.segments].sort((a, b) => b.customers - a.customers)[0]?.slug
  const reach = d.model?.capture?.model?.['20%']
  const focusLabel = focus && (focus.tier === 'High-value' ? 'high-value customers' : `${shortName(focus.name)} customers`)

  return (
    <div className="page" style={{ gap: 28 }}>
      <header className="page-head">
        <div>
          <span className="eyebrow">This week at a glance</span>
          <h1 className="h1 big">{d.totals.customers.toLocaleString('en-US')} regulars are drifting away.</h1>
          <p className="lead" style={{ fontSize: 18, maxWidth: 620 }}>Here's who they are, why they're pulling back, and what to send them this week.</p>
          {d.model?.source === 'pretrained' && !d.store?.demo && (
            <span className="chip butter" style={{ alignSelf: 'flex-start' }}>Scored with the pre-trained model (trained on a US grocery chain): a starting point</span>
          )}
        </div>
        <Link className="btn tomato" to="/win-back">Open campaign kits <Icon.arrow /></Link>
      </header>

      <section aria-label="Key numbers" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        <Kpi label="At-risk regulars" value={d.totals.customers.toLocaleString('en-US')} note="The riskiest 20% of your regular shoppers" />
        <Kpi label="Weekly revenue at risk" value={money0(d.totals.weekly_revenue_at_risk)} color="var(--tomato-text)" note="What they spend each week today" />
        {focus && <Kpi label="Highest value per customer" value={money2(focus.revenue_at_risk_per_customer)} note={`${shortName(focus.name)} group, at risk each week`} />}
        {reach !== undefined ? (
          <Kpi label="Model reach" value={pct0(reach)} color="var(--green)"
            note={<>of drifters found by contacting just 20% ({(reach / 0.2).toFixed(1)}× random). <Link to="/model">About this model</Link></>} />
        ) : d.model && (
          <Kpi label="Model accuracy (ROC-AUC)" value={d.model.roc_auc} color="var(--green)" note={`vs ${d.model.recency_rule_roc_auc} for the days-since-last-visit rule`} />
        )}
      </section>

      {focus && (
        <section aria-label="Where to start" className="dark" style={{ borderRadius: 28, padding: 'clamp(24px, 4vw, 40px)', display: 'flex', flexWrap: 'wrap', gap: 32, alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ flex: '1 1 420px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <span className="chip" style={{ alignSelf: 'flex-start', background: 'var(--tomato)', color: '#FFFFFF' }}>Start here</span>
            <h2 className="head" style={{ margin: 0, fontWeight: 700, fontSize: 'clamp(26px, 3vw, 36px)', lineHeight: 1.1, letterSpacing: '-0.02em' }}>
              Win back your {focus.customers} {focusLabel} first.
            </h2>
            <p style={{ margin: 0, fontSize: 17, lineHeight: 1.55, color: 'var(--on-dark)', maxWidth: 560 }}>
              They're {pct0(focus.customer_share)} of the at-risk list but hold {pct0(focus.share_of_revenue_at_risk)} of the
              revenue at risk: {money2(focus.revenue_at_risk_per_customer)} each, every week.
              {d.focus_why?.perk && !/^none/i.test(d.focus_why.perk) && <> Their campaign leads with a perk: {d.focus_why.perk.replace(/\.$/, '')}.</>}
            </p>
            {d.focus_why && (
              <span style={{ fontSize: 14, color: 'var(--butter)' }}>
                Recommended: highest revenue at risk per customer ({money2(d.focus_why.per_customer)}
                {d.focus_why.others.length > 0 && <> vs {d.focus_why.others.map(money2).join(d.focus_why.others.length > 2 ? ', ' : ' and ')}</>})
              </span>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, paddingTop: 6 }}>
              <Link className="btn cream" to={`/win-back/${focus.slug}`}>See their campaign</Link>
              <Link className="btn ghost-light" to={`/why/${focus.slug}`}>Why they're leaving</Link>
            </div>
          </div>
          <div style={{ flex: '0 1 320px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            {[['Share of at-risk customers', focus.customer_share, 'var(--butter)'], ['Share of revenue at risk', focus.share_of_revenue_at_risk, 'var(--tomato)']].map(([label, v, color], i) => (
              <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingTop: i ? 6 : 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, color: 'var(--on-dark)' }}>
                  <span>{label}</span><span style={{ fontWeight: 700, color: 'var(--cream)' }}>{pct0(v)}</span>
                </div>
                <div style={{ height: 14, borderRadius: 999, background: 'rgba(251,247,239,0.15)', overflow: 'hidden' }} aria-hidden="true">
                  <div style={{ width: pct1(v), height: '100%', background: color }} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section aria-labelledby="seg-h" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
          <h2 id="seg-h" className="h2">Who's drifting</h2>
          <span style={{ fontSize: 14, color: 'var(--muted)' }}>Grouped by value and main reason</span>
        </div>
        {d.small_segments?.length > 0 && (
          <div className="notice butter"><Icon.warning />{d.small_segments.join(', ')} {d.small_segments.length > 1 ? 'have' : 'has'} fewer than 10 customers: treat {d.small_segments.length > 1 ? 'their' : 'its'} patterns as a hint, not a finding.</div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
          {segs.map((s) => <SegmentCard key={s.slug} s={s} look={segmentLook(s, d.focus, largest)} />)}
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <ReasonSplit split={d.reason_split} />
        {d.model?.capture ? <CaptureChart capture={d.model.capture} /> : (
          <div style={{ ...CARD, borderRadius: 22, padding: 26 }}>
            <h2 className="head" style={{ margin: '0 0 6px', fontWeight: 700, fontSize: 22 }}>How many drifters you'll reach</h2>
            <p style={{ margin: 0, fontSize: 15, color: 'var(--muted)' }}>Retrain once to measure reach at 10%, 20% and 30%.</p>
          </div>
        )}
      </section>
    </div>
  )
}
