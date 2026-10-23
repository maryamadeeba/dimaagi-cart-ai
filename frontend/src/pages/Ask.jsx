import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import HowMade from '../components/HowMade.jsx'
import { Markdown, RefChip } from '../components/RichText.jsx'
import { AvatarMark, Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'

const TOOL_NAMES = {
  list_segments: 'list segments', get_segment_reasons: 'segment reasons', search_reviews: 'search reviews',
  search_marketing_trends: 'marketing trends', get_campaign_kit: 'campaign kit',
}
const STARTERS = ['Which group of customers should I focus on first?', 'Why are my high-value customers leaving?',
  'What should I fix before sending a campaign?']
const FOLLOW_UPS = ['What should I send them?', 'What do I fix first?', 'Do shoppers complain about prices?']
const KIND_ORDER = 'SKWTR'

function Answer({ m }) {
  if (m.error) {
    return (
      <div className="bubble-ai" role="alert" style={{ borderColor: 'var(--tomato)' }}>
        <p>{m.error.message}</p>
        {m.error.code === 'no_key' && <p><Link to="/retrain#ai-settings">Add your Gemini key</Link></p>}
      </div>
    )
  }
  const r = m.result
  const invalid = r.cited.filter((c) => !c.valid).map((c) => c.ref)
  const labels = Object.fromEntries(r.cited.map((c) => [c.ref, c.label]))
  const tools = r.tools.map((t) => TOOL_NAMES[t] || t)
  const ungrounded = r.ungrounded_numbers.length
  return (
    <div className="bubble-ai">
      <Markdown text={r.answer} invalid={invalid} labels={labels} />
      <div className="meta">
        <span>{tools.length ? `Tool${tools.length > 1 ? 's' : ''} used: ${tools.join(', ')}` : 'No tools used'}</span>
        {r.validity !== null && (
          <span style={invalid.length ? { color: 'var(--tomato-text)', fontWeight: 600 } : undefined}>
            {invalid.length ? `${invalid.length} citation${invalid.length > 1 ? 's' : ''} not from a source` : 'Citations valid'}
          </span>
        )}
        <span style={ungrounded ? { color: 'var(--tomato-text)', fontWeight: 600 } : undefined}
          title={ungrounded ? r.ungrounded_numbers.map((u) => u.number).join(', ') : undefined}>
          {ungrounded ? `${ungrounded} number${ungrounded > 1 ? 's' : ''} to check: ${r.ungrounded_numbers.map((u) => u.number).join(', ')}` : 'Numbers checked'}
        </span>
        <span>{r.seconds}s</span>
      </div>
      <HowMade how={r.how} kind="chat" compact />
    </div>
  )
}

function Sources({ messages }) {
  const seen = new Map()
  for (const m of messages) for (const c of m.result?.cited || []) if (!seen.has(c.ref)) seen.set(c.ref, c)
  const all = [...seen.values()].sort((a, b) => KIND_ORDER.indexOf(a.ref[0]) - KIND_ORDER.indexOf(b.ref[0]) ||
    a.ref.localeCompare(b.ref, 'en', { numeric: true }))
  const reviews = all.filter((c) => c.ref[0] === 'R' && c.valid)
  const others = all.filter((c) => c.ref[0] !== 'R' || !c.valid)
  return (
    <aside aria-label="Sources" className="card" style={{ flex: '1 1 280px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14, padding: 22 }}>
      <h2 className="head" style={{ margin: 0, fontWeight: 700, fontSize: 20 }}>Sources in this chat</h2>
      {all.length === 0 && <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>Every answer cites where its facts come from. Sources appear here as you ask.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 14, lineHeight: 1.45 }}>
        {others.map((c) => (
          <div key={c.ref} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <RefChip id={c.ref} invalid={!c.valid} />
            <span className="wrap-anywhere">{c.valid ? c.label : 'Not a source any tool returned'}</span>
          </div>
        ))}
        {reviews.length > 0 && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <span style={{ display: 'flex', flexWrap: 'wrap', gap: 4, flexShrink: 0, maxWidth: '55%' }}>
              {reviews.map((c) => <RefChip key={c.ref} id={c.ref} label={c.label} />)}
            </span>
            <span className="wrap-anywhere">Yelp reviews of other grocery stores (1–3★)</span>
          </div>
        )}
      </div>
      <div style={{ marginTop: 6, paddingTop: 14, borderTop: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>
        <span style={{ fontWeight: 700, color: 'var(--ink)' }}>How to read the tags</span>
        <span><strong style={{ color: 'var(--green)' }}>S</strong> your sales data · <strong style={{ color: 'var(--tomato-text)' }}>R</strong> reviews from other stores · <strong>T</strong> marketing reports · <strong>K</strong> campaign kits · <strong>W</strong> reasons analysis</span>
        <span>Every tag is checked: it must come from a tool, and every number must match the source right after it.</span>
      </div>
    </aside>
  )
}

export default function Ask() {
  const { chat, setChat, newChat, health } = useApp()
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const endRef = useRef(null)
  const inputRef = useRef(null)
  const messages = chat.messages

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages.length, pending])

  const send = async (q) => {
    const question = q.trim()
    if (!question || pending) return
    setText('')
    const id = chat.id
    setChat((c) => ({ ...c, messages: [...c.messages, { role: 'user', text: question }] }))
    setPending(true)
    let reply
    try { reply = { role: 'ai', result: await api.chat(id, question) } } catch (e) { reply = { role: 'ai', error: e } }
    setChat((c) => (c.id === id ? { ...c, messages: [...c.messages, reply] } : c))
    setPending(false)
    inputRef.current?.focus()
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text) }
  }
  const kbMissing = health?.kb && (!health.kb.reviews || !health.kb.trends)

  return (
    <div className="page" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>
      <section aria-label="Conversation" style={{ flex: '999 1 520px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <header className="page-head" style={{ alignItems: 'flex-end' }}>
          <div style={{ gap: 6 }}>
            <span className="eyebrow">Ask Dimaagi</span>
            <h1 className="h1" style={{ fontSize: 'clamp(28px, 3.4vw, 40px)' }}>Ask anything about your customers</h1>
          </div>
          {messages.length > 0 && <button type="button" className="sug" onClick={newChat} disabled={pending}>New chat</button>}
        </header>

        {health && !health.has_key && (
          <div className="notice butter"><Icon.warning /><span>The chat uses your Gemini key. <Link to="/retrain#ai-settings">Add it in AI settings</Link>.</span></div>
        )}
        {kbMissing && (
          <div className="notice green"><Icon.info /><span>Review and report search needs both knowledge bases. Until they're built, questions about segments, reasons and kits still work. <Link to="/retrain">Set them up</Link>.</span></div>
        )}

        <div role="log" aria-live="polite" aria-label="Messages" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {messages.map((m, i) => (m.role === 'user' ? (
            <div key={i} className="bubble-me"><span className="sr-only">You: </span>{m.text}</div>
          ) : (
            <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <span className="avatar" aria-hidden="true"><AvatarMark /></span>
              <div style={{ minWidth: 0, flex: 1 }}><span className="sr-only">Dimaagi: </span><Answer m={m} /></div>
            </div>
          )))}
          {pending && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }} role="status">
              <span className="avatar" aria-hidden="true"><AvatarMark /></span>
              <span style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--muted)', fontSize: 15 }}><Icon.spinner />Checking your data…</span>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingTop: 4 }}>
          {(messages.length ? FOLLOW_UPS : STARTERS).map((q) => (
            <button key={q} type="button" className="sug" onClick={() => send(q)} disabled={pending}>{q}</button>
          ))}
        </div>

        <form onSubmit={(e) => { e.preventDefault(); send(text) }}
          style={{ display: 'flex', gap: 10, alignItems: 'flex-end', background: '#FFFFFF', border: '1.5px solid var(--border)', borderRadius: 22, padding: '10px 10px 10px 18px' }}>
          <label htmlFor="ask" className="sr-only">Your question</label>
          <textarea id="ask" ref={inputRef} rows={2} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
            placeholder="Ask about your at-risk customers, why they're leaving, or what to send…"
            style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', resize: 'none', font: "16px/1.5 'Figtree', sans-serif", color: 'var(--ink)', background: 'transparent', padding: '8px 0' }} />
          <button type="submit" aria-label="Send" disabled={pending || !text.trim()}
            style={{ flexShrink: 0, width: 46, height: 46, borderRadius: 14, border: 'none', background: 'var(--tomato)', color: '#FFFFFF', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', opacity: pending || !text.trim() ? 0.6 : 1 }}>
            <Icon.send />
          </button>
        </form>
      </section>

      <Sources messages={messages} />
    </div>
  )
}
