import { useEffect, useState } from 'react'
import { dataFolder, pickFolder } from '../api.js'
import { Icon } from '../icons.jsx'
import { useApp } from '../state.jsx'
import { ConfirmDialog } from './Regenerate.jsx'

const SOURCE = {
  env: 'Set by the DIMAAGI_DATA_DIR environment variable',
  config: 'Chosen in these settings',
  default: 'The default folder',
}

// Pick a folder and check it. requireExisting: only accept an existing Dimaagi Cart folder (the welcome screen).
export function useFolderPicker({ requireExisting = false } = {}) {
  const [pending, setPending] = useState(null)        // { dir, check }
  const [error, setError] = useState(null)
  const choose = async () => {
    setError(null)
    const dir = await pickFolder?.()
    if (!dir) return
    const check = await dataFolder.check(dir)
    if (!check.ok) return setError(check.message)
    if (requireExisting && check.kind !== 'existing') {
      return setError("That folder isn't a Dimaagi Cart folder yet. Choose one that has Dimaagi Cart's models or stores in it, or start with the demo store.")
    }
    setPending({ dir, check })
  }
  return { pending, setPending, error, setError, choose }
}

export function Restarting() {
  return (
    <div className="restarting" role="status" aria-live="assertive">
      <Icon.spinner /> Restarting the engine with the new folder…
    </div>
  )
}

export default function DataFolder() {
  const { health } = useApp()
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)
  const picker = useFolderPicker()
  useEffect(() => { dataFolder?.get().then(setInfo) }, [health?.data_dir])

  const use = async (dir) => {
    picker.setPending(null)
    setBusy(true)
    const r = await dataFolder.set(dir)
    setBusy(false)                      // on success the window reloads before this matters
    if (!r.ok) picker.setError(r.message || "The engine didn't start with that folder.")
  }
  const locked = info?.source === 'env'

  return (
    <section className="card" aria-labelledby="data-folder-h" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h2 id="data-folder-h" className="h2 sm">Data folder</h2>
      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>
        Where Dimaagi Cart keeps your stores, scores and knowledge bases. Point it at a folder you already use (for example
        your project folder) to work with that data.
      </p>
      <div style={{ background: 'var(--cream)', borderRadius: 14, padding: '10px 12px', fontSize: 14, lineHeight: 1.5 }}>
        <code className="wrap-anywhere" style={{ display: 'block' }}>{info?.dir || health?.data_dir || '…'}</code>
        <span className="muted">{info ? SOURCE[info.source] : 'Change it in the desktop app'}</span>
      </div>
      {dataFolder && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          <button type="button" className="btn outline" onClick={picker.choose} disabled={locked || busy}>Choose folder…</button>
          {info?.source === 'config' && (
            <button type="button" className="btn outline" onClick={() => use(null)} disabled={busy}>Use the default</button>
          )}
        </div>
      )}
      {locked && <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>To change it here, remove DIMAAGI_DATA_DIR from your environment variables first.</p>}
      {picker.error && <div className="notice tomato" role="alert">{picker.error}</div>}
      {busy && <Restarting />}
      <ConfirmDialog open={!!picker.pending} title="Use this folder?" confirmLabel="Use it and restart the engine"
        onConfirm={() => use(picker.pending.dir)} onCancel={() => picker.setPending(null)}>
        <p style={{ margin: '0 0 8px' }}><code className="wrap-anywhere">{picker.pending?.dir}</code></p>
        <p style={{ margin: '0 0 8px' }}>{picker.pending?.check.message}</p>
        {picker.pending?.check.keyInEnv && <p style={{ margin: 0, fontSize: 14 }}>Its <code>.env</code> has a Gemini key, which Dimaagi Cart will use unless you saved one in the app.</p>}
        <p style={{ margin: '8px 0 0', fontSize: 14, color: 'var(--muted)' }}>Nothing is moved or deleted; the current folder stays as it is.</p>
      </ConfirmDialog>
    </section>
  )
}
