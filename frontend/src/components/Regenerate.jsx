import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'
import JobSteps from './JobSteps.jsx'

const STEPS = [{ key: 'reasons', label: 'Rewrite reasons' }, { key: 'kits', label: 'Rewrite campaign kits' }]

// A modal confirm built on <dialog>: focus is trapped, Esc cancels.
export function ConfirmDialog({ open, title, children, confirmLabel, onConfirm, onCancel }) {
  const ref = useRef(null)
  useEffect(() => {
    const d = ref.current
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="dlg-title" onCancel={(e) => { e.preventDefault(); onCancel() }}>
      <h2 id="dlg-title" className="h2 sm">{title}</h2>
      <div style={{ fontSize: 15, lineHeight: 1.55, color: 'var(--body)' }}>{children}</div>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        <button type="button" className="btn outline" onClick={onCancel}>Cancel</button>
        <button type="button" className="btn tomato" onClick={onConfirm} autoFocus>{confirmLabel}</button>
      </div>
    </dialog>
  )
}

// Reruns Gemini for one segment (slug) or for every segment (no slug). what: reasons | kit | both
export default function Regenerate({ slug, what, label, segmentName }) {
  const { health, jobs, track, busy } = useApp()
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState(null)
  const job = jobs.regenerate
  const needsTrends = what !== 'reasons'
  const blocker = !health?.has_key ? 'Needs your Gemini key (AI settings on the Retrain screen).'
    : !health?.kb?.reviews ? 'Needs the reviews knowledge base (Retrain screen).'
      : needsTrends && !health?.kb?.trends ? 'Needs the marketing trends knowledge base (Retrain screen).' : null
  const calls = what === 'both' ? 'two' : 'one'
  const start = async () => {
    setOpen(false); setErr(null)
    try { track(await (slug ? api.regenerate(slug, what) : api.regenerateAll(what))) } catch (e) { setErr(e.message) }
  }
  const running = job?.status === 'running'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
      <button type="button" className="btn outline" disabled={!!blocker || busy} onClick={() => setOpen(true)}
        aria-describedby={blocker ? `regen-why-${slug || 'all'}` : undefined}>
        {running ? <Icon.spinner /> : <Icon.retrain />}{label}
      </button>
      {blocker && <span id={`regen-why-${slug || 'all'}`} style={{ fontSize: 13, color: 'var(--muted)', maxWidth: 280, textAlign: 'right' }}>
        {blocker} {!health?.has_key && <Link to="/retrain#ai-settings">Add it</Link>}
      </span>}
      {err && <div className="notice tomato" role="alert">{err}</div>}
      {job && job.status !== 'done' && (
        <div className="card" style={{ padding: 16, minWidth: 280 }}>
          <JobSteps job={job} steps={STEPS} />
          {job.status === 'error' && <div className="notice tomato" role="alert" style={{ marginTop: 10 }}>{job.error}</div>}
        </div>
      )}
      <ConfirmDialog open={open} title={`${label}?`} confirmLabel="Use Gemini and rewrite" onConfirm={start} onCancel={() => setOpen(false)}>
        <p style={{ margin: '0 0 8px' }}>
          This asks Gemini again{segmentName ? ` for ${segmentName}` : ' for every segment'}: about {calls} call{calls === 'one' ? '' : 's'} per
          segment on your key, counted against your daily quota. The current text is replaced when the new one is ready; its code
          checks are shown under “How this was made”.
        </p>
        <p style={{ margin: 0, color: 'var(--muted)', fontSize: 14 }}>Only short review snippets and segment numbers are sent.</p>
      </ConfirmDialog>
    </div>
  )
}
