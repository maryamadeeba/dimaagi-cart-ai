import { useState } from 'react'
import { api, dataFolder } from '../api.js'
import { ConfirmDialog } from '../components/Regenerate.jsx'
import { Restarting, useFolderPicker } from '../components/DataFolder.jsx'
import { LogoMark, Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'

// First launch: connect your own sales data, or look around the demo store first.
export default function Welcome({ onConnect }) {
  const { refresh, health } = useApp()
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const picker = useFolderPicker({ requireExisting: true })
  const open = async () => {
    const dir = picker.pending.dir
    picker.setPending(null)
    setBusy(true)
    const r = await dataFolder.set(dir, { fromWelcome: true })
    setBusy(false)
    if (!r.ok) setErr(r.message || "The engine didn't start with that folder.")
  }
  const demo = async () => {
    try { await api.activateStore('demo'); await refresh() } catch (e) { setErr(e.message) }
  }
  return (
    <main className="welcome" id="main" tabIndex={-1}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <LogoMark size={44} /><span className="head" style={{ fontWeight: 800, fontSize: 30, color: 'var(--cream)', letterSpacing: '-0.02em' }}>Dimaagi Cart</span>
      </div>
      <h1 className="h1 big" style={{ color: 'var(--cream)', maxWidth: 760, textAlign: 'center' }}>Your store's smart cart: spot drifting regulars, see why, and win them back.</h1>
      <p style={{ margin: 0, fontSize: 18, color: 'var(--on-dark)', maxWidth: 620, textAlign: 'center', lineHeight: 1.5 }}>
        A churn model scores every regular shopper, and an AI assistant turns the reasons into a ready-to-send campaign. Everything runs on this computer.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 18, width: '100%', maxWidth: 820 }}>
        <button type="button" className="welcome-choice" onClick={onConnect}>
          <span className="step-n" style={{ width: 48, height: 48, borderRadius: 14 }} aria-hidden="true"><Icon.upload /></span>
          <span className="head" style={{ fontWeight: 700, fontSize: 24 }}>Connect my sales data</span>
          <span style={{ fontSize: 15, color: 'var(--muted)', lineHeight: 1.5 }}>Import a CSV or Excel export from your till or POS. About five minutes.</span>
        </button>
        <button type="button" className="welcome-choice" onClick={demo}>
          <span className="step-n ai" style={{ width: 48, height: 48, borderRadius: 14 }} aria-hidden="true"><Icon.dashboard /></span>
          <span className="head" style={{ fontWeight: 700, fontSize: 24 }}>Explore the demo store</span>
          <span style={{ fontSize: 15, color: 'var(--muted)', lineHeight: 1.5 }}>{health?.app?.demo_label || 'A real, anonymised US grocery dataset'}. Switch to your own data any time.</span>
        </button>
      </div>
      {dataFolder && (
        <button type="button" className="welcome-link" onClick={picker.choose} disabled={busy}>
          Open an existing Dimaagi Cart folder…
        </button>
      )}
      {busy && <Restarting />}
      {(err || picker.error) && <div className="notice tomato" role="alert">{err || picker.error}</div>}
      <ConfirmDialog open={!!picker.pending} title="Open this Dimaagi Cart folder?" confirmLabel="Open it"
        onConfirm={open} onCancel={() => picker.setPending(null)}>
        <p style={{ margin: '0 0 8px' }}><code className="wrap-anywhere">{picker.pending?.dir}</code></p>
        <p style={{ margin: 0 }}>{picker.pending?.check.message}</p>
      </ConfirmDialog>
    </main>
  )
}
