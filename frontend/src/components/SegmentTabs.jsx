import { useRef } from 'react'
import { tabLabel } from '../format.js'

// Accessible tabs: real buttons, arrow keys move between groups, the panel is labelled by the active tab.
export default function SegmentTabs({ segments, value, onChange, panelId }) {
  const refs = useRef([])
  const onKey = (e, i) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key]
    let next = step !== undefined ? (i + step + segments.length) % segments.length : null
    if (e.key === 'Home') next = 0
    if (e.key === 'End') next = segments.length - 1
    if (next === null) return
    e.preventDefault()
    onChange(segments[next].slug)
    refs.current[next]?.focus()
  }
  return (
    <div role="tablist" aria-label="Customer group" className="tabs">
      {segments.map((s, i) => (
        <button key={s.slug} ref={(el) => (refs.current[i] = el)} type="button" role="tab" className="tab"
          id={`tab-${s.slug}`} aria-selected={s.slug === value} aria-controls={panelId}
          tabIndex={s.slug === value ? 0 : -1} onClick={() => onChange(s.slug)} onKeyDown={(e) => onKey(e, i)}>
          {tabLabel(s)}
        </button>
      ))}
    </div>
  )
}
