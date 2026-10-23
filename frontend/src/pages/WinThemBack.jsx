import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, download } from '../api.js'
import { ConfirmText } from '../components/RichText.jsx'
import HowMade from '../components/HowMade.jsx'
import Regenerate from '../components/Regenerate.jsx'
import SegmentTabs from '../components/SegmentTabs.jsx'
import SetupCard, { ErrorCard, Loading } from '../components/SetupCard.jsx'
import { money2, moneyShort, orderSegments, pct0, shortName } from '../format.js'
import { Icon } from '../icons.jsx'
import { PREFIX } from '../storage.js'
import { useApp } from '../state.jsx'

const dayOf = (plan, channel) => plan.find((s) => s.channel.toLowerCase().includes(channel))?.day
const SIGN_OFF = /(?:^|\s)((?:Warmly|Warm regards|Kind regards|Best wishes|Best|Sincerely|Cheers|Thanks|Thank you|See you soon|With gratitude|Gratefully|Yours),)\s*(\[STORE NAME\]|[A-Z][^.!?\n]{0,40})?$/i

// Email body -> paragraphs and the sign-off, so the signature can sit below the button as in the design
function splitEmail(body) {
  const paras = body.split(/\n\s*\n|\n/).map((p) => p.trim()).filter(Boolean)
  const last = paras[paras.length - 1] || ''
  const prev = paras[paras.length - 2] || ''
  if (paras.length > 1 && last.length <= 60 && prev.length <= 40 && SIGN_OFF.test(`${prev} ${last}`) && SIGN_OFF.test(` ${prev}`)) {
    return { paragraphs: paras.slice(0, -2), signature: [prev, last] }
  }
  const m = last.match(SIGN_OFF)
  if (m) {
    const rest = last.slice(0, m.index).trim()
    return { paragraphs: [...paras.slice(0, -1), ...(rest ? [rest] : [])], signature: [m[1], m[2]].filter(Boolean) }
  }
  return { paragraphs: paras, signature: null }
}

// Checklist ticks are remembered per segment on this computer (keyed by the item text, so a rewritten kit starts fresh)
function useChecklist(slug) {
  const key = `${PREFIX}checklist.${slug}`
  const read = () => {
    try { return new Set(JSON.parse(localStorage.getItem(key) || '[]')) } catch { return new Set() }
  }
  const [done, setDone] = useState(read)
  useEffect(() => { setDone(read()) }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = (item) => {
    const next = new Set(done)
    next.has(item) ? next.delete(item) : next.add(item)
    setDone(next)
    try { localStorage.setItem(key, JSON.stringify([...next])) } catch { /* storage unavailable: ticks last this session */ }
  }
  return [done, toggle]
}

function toMarkdown(d, store) {
  const k = d.kit
  const c = d.checks
  const o = c.offer
  const refs = (list) => (list?.length ? ` (${list.join(', ')})` : '')
  return [
    `# Win-back campaign kit: ${d.name}`, '',
    `${d.customers} customers · ${money2(d.weekly_revenue_at_risk)} / week at risk`, '',
    'Remove every [CONFIRM] tag (and make sure the claim is true) before sending. Offers are suggestions.', '',
    `**Goal:** ${k.goal}`, '',
    `## Offer: ${k.offer.headline}`, k.offer.details, '',
    `- Discount: ${moneyShort(o.discount)} off a ${moneyShort(o.min_basket)} basket (${pct0(o.discount_rate)} of the basket)`,
    `- Usual week (median spend): ${o.median_spend != null ? money2(o.median_spend) : 'unknown'}`,
    `- Perk: ${k.offer.non_monetary_perk}`,
    `- Why this offer: ${k.offer.why_this_offer}${refs(k.offer.citations)}`, '',
    '## Before you send', ...k.owner_checklist.map((x) => `- [ ] ${x}`), '',
    `## Email (day ${dayOf(k.send_plan, 'email') ?? 1})`, `From: ${store}`, `**Subject:** ${k.email.subject}`,
    `**Preview:** ${k.email.preview_text}`, '', k.email.body, '', `**Button:** ${k.email.call_to_action}${refs(k.email.citations)}`, '',
    `## SMS (~${c.sms_send_chars} characters when sent, opted-in customers only)`, `> ${k.sms.text}`, '',
    `## Social post (${k.social_post.platform})`, `**Photo idea:** ${k.social_post.concept}`, `**Hook:** ${k.social_post.hook}`, '',
    k.social_post.caption, '',
    '## Send plan', '| Day | Channel | Action |', '|---|---|---|',
    ...k.send_plan.map((s) => `| ${s.day} | ${s.channel} | ${s.action} |`), '',
    '## Measure', ...k.measurement.map((x) => `- ${x}`), '',
    '## Risks', k.risks, '',
    '## Sources', `- ${d.sources.reviews} reviews from other grocery stores (Yelp, a proxy voice)`,
    ...Object.entries(d.sources.refs).map(([r, label]) => `- ${r}: ${label}`), '',
  ].join('\n')
}

function Check({ ok, children }) {
  return (
    <span className={`chip ${ok ? 'ok' : 'warn'}`} style={{ height: 30 }}>
      {ok ? <Icon.check /> : <Icon.cross />}<span className="sr-only">{ok ? 'Passed: ' : 'Needs a look: '}</span>{children}
    </span>
  )
}

function Stat({ k, v }) {
  return <div className="stat"><span className="k">{k}</span><span className="v num">{v}</span></div>
}

export default function WinThemBack() {
  const { dashboard, dashError, version } = useApp()
  const { slug } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const segs = dashboard ? orderSegments(dashboard.segments, dashboard.focus) : []
  const current = slug || dashboard?.focus
  const [done, toggle] = useChecklist(current)
  const store = dashboard?.store_name || '[STORE NAME]'

  useEffect(() => {
    if (!current) return
    let live = true
    setData(null); setError(null)
    api.kit(current).then((d) => live && setData(d), (e) => live && setError(e))
    return () => { live = false }
  }, [current, version])

  const head = (
    <header className="page-head" style={{ alignItems: 'flex-end' }}>
      <div>
        <span className="eyebrow">Win them back</span>
        <h1 className="h1">Your campaign kit, ready to send</h1>
        <p className="lead" style={{ maxWidth: 640 }}>Fix first, then promise. Every message is checked before it reaches you.</p>
      </div>
      <button type="button" className="btn outline" disabled={!data}
        onClick={() => download(`win-back-kit-${current}.md`, toMarkdown(data, store), 'text/markdown')}>
        <Icon.download />Export kit
      </button>
    </header>
  )
  if (dashError) {
    return <div className="page">{head}{dashError.code === 'missing_output' ? <SetupCard message={dashError.message} /> : <ErrorCard error={dashError} />}</div>
  }

  let body
  if (error?.code === 'missing_output') body = (
    <>
      <SetupCard title="Write the campaign kits" message={error.message} />
      {current && <Regenerate what="kit" label="Write kits for all segments" />}
    </>
  )
  else if (error) body = <ErrorCard error={error} />
  else if (!data) body = <Loading />
  else {
    const k = data.kit
    const c = data.checks
    const o = c.offer
    const { paragraphs, signature } = splitEmail(k.email.body)
    const highBasket = o.median_spend && o.min_basket >= 2 * o.median_spend
    const gentler = o.median_spend && Math.max(Math.ceil(o.median_spend), Math.round((o.median_spend * 1.5) / 5) * 5)
    const perk = /^none\.?$/i.test(k.offer.non_monetary_perk.trim()) ? 'None: a simple discount keeps it easy.' : k.offer.non_monetary_perk
    body = (
      <>
        <div aria-label="Automatic checks" role="list" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <span role="listitem"><Check ok={c.citation_validity === 1}>{c.citation_validity === 1 ? 'Citations valid' : `${c.invalid_citations.length} invalid citations`}</Check></span>
          <span role="listitem"><Check ok={c.sms_ok}>SMS {c.sms_send_chars} / 160</Check></span>
          <span role="listitem"><Check ok={c.subject_ok}>Subject {c.subject_chars} / 60</Check></span>
          <span role="listitem"><Check ok={o.economics_ok}>{o.threshold_above_median ? 'Offer above median spend' : 'Offer below median spend'}</Check></span>
          <span role="listitem"><Check ok={!c.unflagged_claims.length}>{c.unflagged_claims.length ? `${c.unflagged_claims.length} untagged promises` : 'No unchecked promises'}</Check></span>
          {c.unsupported_numbers.length > 0 && <span role="listitem"><Check ok={false}>Numbers to verify: {c.unsupported_numbers.join(', ')}</Check></span>}
          <span role="listitem" className="chip butter" style={{ height: 30 }}>{c.confirm_flags} [CONFIRM] lines to verify</span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Regenerate slug={current} what="kit" label="Regenerate this kit" segmentName={shortName(data.name)} />
        </div>
        {data.too_small && <div className="notice butter"><Icon.warning />Only {data.customers} customers in this group: test the offer on a few before sending to all.</div>}
        <section style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'stretch' }}>
          <div className="dark" style={{ flex: '999 1 460px', minWidth: 0, borderRadius: 26, padding: 30, display: 'flex', flexDirection: 'column', gap: 18 }}>
            <span className="lbl" style={{ color: 'var(--butter)' }}>The offer · {shortName(data.name)}</span>
            <h2 className="head" style={{ margin: 0, fontWeight: 700, fontSize: 'clamp(26px, 3vw, 36px)', lineHeight: 1.1, letterSpacing: '-0.02em' }}>{k.offer.headline}</h2>
            <p style={{ margin: 0, fontSize: 16, lineHeight: 1.55, color: 'var(--on-dark)' }}>{k.offer.why_this_offer}</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12 }}>
              <Stat k="Discount" v={moneyShort(o.discount)} />
              <Stat k="Minimum basket" v={moneyShort(o.min_basket)} />
              <Stat k="Of the basket" v={pct0(o.discount_rate)} />
              <Stat k="Usual week" v={o.median_spend != null ? money2(o.median_spend) : '—'} />
            </div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', background: 'var(--cream)', color: 'var(--ink)', borderRadius: 16, padding: '14px 16px', fontSize: 15, lineHeight: 1.5 }}>
              <Icon.gift /><span><strong>Perk:</strong> {perk}</span>
            </div>
            {highBasket && (
              <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--butter)' }}>
                Your call: {moneyShort(o.min_basket)} is about {(o.min_basket / o.median_spend).toFixed(0)}× this group's usual basket.
                Lowering it to about ${gentler} may bring more people back.
              </div>
            )}
          </div>

          <div className="card" style={{ flex: '1 1 320px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <h2 className="h2 sm">Before you send</h2>
              <span style={{ fontSize: 13, color: 'var(--muted)' }}>{done.size ? `${[...done].filter((x) => k.owner_checklist.includes(x)).length} of ` : ''}{k.owner_checklist.length} steps</span>
            </div>
            <p style={{ margin: '0 0 4px', fontSize: 14, color: 'var(--muted)' }}>Do these first, so every [CONFIRM] line is true.</p>
            {k.owner_checklist.map((item) => (
              <label key={item} className="check">
                <input type="checkbox" checked={done.has(item)} onChange={() => toggle(item)} />
                <span>{item}</span>
              </label>
            ))}
          </div>
        </section>

        <section style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>
          <article className="card" aria-label="Email" style={{ flex: '999 1 460px', minWidth: 0, padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span className="lbl">Email · day {dayOf(k.send_plan, 'email') ?? 1}</span>
              <div style={{ fontSize: 14, color: 'var(--muted)' }}>From: {store}</div>
              <div style={{ fontSize: 19, fontWeight: 700 }}><ConfirmText text={k.email.subject} /></div>
              <div style={{ fontSize: 14, color: 'var(--muted)' }}><ConfirmText text={k.email.preview_text} /></div>
            </div>
            <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 14, fontSize: 16, lineHeight: 1.6 }}>
              {paragraphs.map((p, i) => <p key={i} style={{ margin: 0 }}><ConfirmText text={p} /></p>)}
              <div style={{ paddingTop: 6 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', minHeight: 44, padding: '0 22px', borderRadius: 999, background: 'var(--tomato)', color: '#FFFFFF', fontWeight: 600 }}>{k.email.call_to_action}</span>
              </div>
              {signature && <div style={{ fontSize: 15 }}>{signature[0]}{signature[1] && <><br />{signature[1]}</>}</div>}
            </div>
          </article>

          <div style={{ flex: '1 1 300px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 20 }}>
            <article className="card" aria-label="SMS" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span className="lbl">SMS · day {dayOf(k.send_plan, 'sms') ?? '—'}</span>
                <span style={{ fontSize: 13, color: 'var(--muted)' }}>opted-in only</span>
              </div>
              <div style={{ background: 'var(--line)', borderRadius: 24, padding: 18, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center' }}>Text message</span>
                <div style={{ alignSelf: 'flex-start', maxWidth: '92%', background: '#FFFFFF', borderRadius: '18px 18px 18px 6px', padding: '12px 14px', fontSize: 15, lineHeight: 1.45 }}>{k.sms.text}</div>
              </div>
            </article>

            <article className="card" aria-label="Social post" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span className="lbl">Social post</span>
                <span style={{ fontSize: 13, color: 'var(--muted)' }}>{k.social_post.platform}</span>
              </div>
              <div style={{ aspectRatio: '4 / 3', borderRadius: 16, background: 'var(--green-tint)', border: '1.5px dashed var(--sage)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, color: 'var(--green)', textAlign: 'center', padding: 16 }}>
                <Icon.photo />
                <span style={{ fontSize: 14, fontWeight: 600 }}>Your photo: {k.social_post.concept}</span>
              </div>
              <div style={{ fontWeight: 700, fontSize: 15 }}><ConfirmText text={k.social_post.hook} /></div>
              <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: 'var(--body)' }}><ConfirmText text={k.social_post.caption} /></p>
            </article>
          </div>
        </section>

        <section className="card" aria-labelledby="plan-h" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
            <h2 id="plan-h" className="head" style={{ margin: 0, fontWeight: 700, fontSize: 22 }}>Two-week send plan</h2>
            <span style={{ fontSize: 14, color: 'var(--muted)' }}>Short and deliberate, ending with a friendly goodbye</span>
          </div>
          <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
            {k.send_plan.map((s, i) => (
              <li key={i} style={{ background: 'var(--cream)', borderRadius: 18, padding: 18, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="head" style={{ fontWeight: 700, fontSize: 20 }}>Day {s.day}</span>
                  <span className="chip" style={{ height: 26, background: '#FFFFFF', color: 'var(--ink)', border: '1px solid var(--border)' }}>{s.channel}</span>
                </div>
                <span style={{ fontSize: 15, lineHeight: 1.5 }}>{s.action}</span>
              </li>
            ))}
          </ol>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 12, paddingTop: 14, borderTop: '1px solid var(--line)', fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>
            <span style={{ flex: '1 1 320px' }}>Built from: {data.sources.reviews} reviews from other stores · {data.sources.trends.join(' · ')}</span>
            <span style={{ flex: '1 1 260px' }}>Measure: {k.measurement.join(' · ')}</span>
          </div>
        </section>
        <HowMade how={data.how} kind="kit" />
      </>
    )
  }

  return (
    <div className="page" style={{ gap: 22 }}>
      {head}
      {segs.length > 0 && <SegmentTabs segments={segs} value={current} onChange={(s) => navigate(`/win-back/${s}`, { replace: true })} panelId="kit-panel" />}
      <div id="kit-panel" role="tabpanel" aria-labelledby={current ? `tab-${current}` : undefined} style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
        {body}
      </div>
    </div>
  )
}
