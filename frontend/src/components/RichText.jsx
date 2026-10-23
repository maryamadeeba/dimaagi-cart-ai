// Renders model text: [CONFIRM] sentences highlighted, refs like [S_highvalue] or [R3, R4] as coloured chips,
// and (for chat answers) a small Markdown subset: paragraphs, bullet and numbered lists, **bold**.
const REF = /^([RT]\d+|[SKW]_[a-z]+)$/

export function RefChip({ id, invalid, label }) {
  const kind = id[0]
  return (
    <span className={`ref ${kind}${invalid ? ' invalid' : ''}`}
      title={invalid ? 'Not a source any tool returned' : label || undefined}>
      {id}
    </span>
  )
}

// Inline: **bold** and [refs]; anything else in brackets (e.g. [STORE NAME]) stays as text
export function Inline({ text, invalid = [], labels = {} }) {
  const parts = String(text).split(/(\*\*[^*]+\*\*|\[[^\]]+\])/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={i}>{p.slice(2, -2)}</strong>
    if (p.startsWith('[') && p.endsWith(']')) {
      const ids = p.slice(1, -1).split(',').map((x) => x.trim())
      if (ids.every((x) => REF.test(x))) {
        return ids.map((x) => <RefChip key={`${i}-${x}`} id={x} invalid={invalid.includes(x)} label={labels[x]} />)
      }
    }
    return p
  })
}

// Customer copy: sentences that carry [CONFIRM] get the butter highlight
export function ConfirmText({ text }) {
  const sentences = String(text).split(/(?<=[.!?])\s+/)
  return sentences.map((s, i) => (
    <span key={i}>
      {i > 0 && ' '}
      {s.includes('[CONFIRM]') ? <span className="confirm">{s}</span> : s}
    </span>
  ))
}

export function Markdown({ text, invalid, labels }) {
  const blocks = []
  let list = null
  for (const raw of String(text).split('\n')) {
    const line = raw.trimEnd()
    const bullet = line.match(/^\s*(?:[-*•])\s+(.*)$/)
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/)
    if (bullet || numbered) {
      const type = bullet ? 'ul' : 'ol'
      if (!list || list.type !== type) blocks.push((list = { type, items: [] }))
      list.items.push((bullet || numbered)[1])
    } else if (line.trim()) {
      list = null
      blocks.push({ type: 'p', text: line })
    } else {
      list = null
    }
  }
  return blocks.map((b, i) => {
    if (b.type === 'p') return <p key={i}><Inline text={b.text} invalid={invalid} labels={labels} /></p>
    const L = b.type
    return (
      <L key={i}>
        {b.items.map((it, j) => <li key={j}><Inline text={it} invalid={invalid} labels={labels} /></li>)}
      </L>
    )
  })
}
