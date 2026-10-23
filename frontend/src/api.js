// The only place that talks to the backend. In Electron the preload script exposes {port, token};
// in a plain browser (npm run dev) calls go to /api and the Vite proxy adds the token.
const desktop = typeof window !== 'undefined' ? window.dimaagi : undefined
const BASE = desktop ? `http://127.0.0.1:${desktop.port}` : ''

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || `Request failed (${status})`)
    this.status = status
    this.code = body?.error
    this.what = body?.what
    this.body = body
  }
}

async function request(path, { method = 'GET', json, form } = {}) {
  const headers = {}
  if (desktop?.token) headers['X-Dimaagi-Token'] = desktop.token
  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = form
  }
  let res
  try {
    res = await fetch(`${BASE}/api${path}`, { method, headers, body })
  } catch {
    throw new ApiError(0, { error: 'offline', message: "Can't reach the Dimaagi Cart engine. Try restarting the app." })
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, data)
  return data
}

export const api = {
  health: () => request('/health'),
  dashboard: () => request('/dashboard'),
  reasons: (slug) => request(`/segments/${encodeURIComponent(slug)}/reasons`),
  kit: (slug) => request(`/segments/${encodeURIComponent(slug)}/kit`),
  chat: (conversationId, message) =>
    request('/chat', { method: 'POST', json: { conversation_id: conversationId, message } }),
  retrain: (files) => {
    const form = new FormData()
    for (const f of files) form.append('files', f, f.name)
    return request('/retrain', { method: 'POST', form })
  },
  job: (id) => request(`/jobs/${encodeURIComponent(id)}`),
  buildKb: (kind, sourcePath) => request('/setup/build-kb', { method: 'POST', json: { kind, source_path: sourcePath } }),
  settings: () => request('/settings'),
  saveSettings: (values) => request('/settings', { method: 'POST', json: values }),
  customers: (params) => request(`/customers?${new URLSearchParams(params)}`),
  customer: (id) => request(`/customers/${encodeURIComponent(id)}`),
  model: () => request('/model'),
  regenerate: (slug, what) => request(`/segments/${encodeURIComponent(slug)}/regenerate`, { method: 'POST', json: { what } }),
  regenerateAll: (what = 'both') => request('/regenerate', { method: 'POST', json: { what } }),
  activateStore: (slug) => request('/stores/activate', { method: 'POST', json: { slug } }),
  showWelcome: () => request('/app/welcome', { method: 'POST' }),
  importUpload: (file) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return request('/import/upload', { method: 'POST', form })
  },
  importAnalyze: (id, body) => request(`/import/${encodeURIComponent(id)}/analyze`, { method: 'POST', json: body }),
  importRun: (id, body) => request(`/import/${encodeURIComponent(id)}/run`, { method: 'POST', json: body }),
  template: async () => {
    const headers = desktop?.token ? { 'X-Dimaagi-Token': desktop.token } : {}
    const res = await fetch(`${BASE}/api/import/template`, { headers })
    if (!res.ok) throw new ApiError(res.status, {})
    return res.text()
  },
}

// Save text as a file (Electron shows its save dialog)
export function download(name, text, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// Folder picker and the data-folder setting when running in Electron; the browser falls back to typing a path.
export const pickFolder = desktop?.pickFolder
export const dataFolder = desktop?.dataFolder
