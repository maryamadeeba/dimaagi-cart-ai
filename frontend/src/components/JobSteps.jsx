import { Icon } from '../icons.jsx'

const STATUS_TEXT = { pending: 'Waiting', running: 'Running', done: 'Done', skipped: 'Skipped', error: 'Failed' }

// Step-by-step progress for a background job. `hints` gives the idle description of each step.
export default function JobSteps({ job, steps, aiKeys = [] }) {
  const live = job ? Object.fromEntries(job.steps.map((s) => [s.key, s])) : {}
  return (
    <ol className="steps" aria-live="polite">
      {steps.map((s, i) => {
        const j = live[s.key]
        const status = j?.status
        return (
          <li key={s.key}>
            <span className={`step-n ${status && status !== 'pending' ? status : aiKeys.includes(s.key) ? 'ai' : ''}`}
              aria-hidden="true">
              {status === 'running' ? <Icon.spinner /> : status === 'done' ? <Icon.check /> :
                status === 'error' ? <Icon.cross /> : i + 1}
            </span>
            <div>
              <div style={{ fontWeight: 700 }}>
                {s.label}
                {status && status !== 'pending' && <span className="sr-only"> ({STATUS_TEXT[status]})</span>}
              </div>
              <div style={{ fontSize: 14, color: status === 'error' ? 'var(--tomato-text)' : 'var(--muted)' }}>
                {j?.detail || s.hint}
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
