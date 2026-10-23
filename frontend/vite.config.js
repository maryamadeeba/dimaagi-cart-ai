import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: run the backend with `python -m src.api.app --port 8765 --token dev --dev`, then `npm run dev`.
// The proxy adds the launch token, so the browser never needs it. Override with DIMAAGI_API_PORT / DIMAAGI_TOKEN (legacy WINBACK_ names still work).
const port = process.env.DIMAAGI_API_PORT || process.env.WINBACK_API_PORT || 8765   // WINBACK_: legacy alias
const token = process.env.DIMAAGI_TOKEN || process.env.WINBACK_TOKEN || 'dev'      // WINBACK_: legacy alias

// Strict CSP for the built app only (the dev server needs an inline React refresh script)
const CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; " +
  "img-src 'self' data: blob:; connect-src 'self' http://127.0.0.1:*"
const csp = {
  name: 'dimaagi-csp',
  apply: 'build',
  transformIndexHtml: (html) =>
    html.replace('<meta charset="utf-8" />', `<meta charset="utf-8" />
    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`),
}

export default defineConfig({
  plugins: [react(), csp],
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: `http://127.0.0.1:${port}`, changeOrigin: true, headers: { 'X-Dimaagi-Token': token } },
    },
  },
  build: { outDir: 'dist', assetsInlineLimit: 0 },
})
