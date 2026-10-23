import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Fonts are bundled with the app (woff2), so there are no runtime requests to Google Fonts
import '@fontsource/figtree/latin-400.css'
import '@fontsource/figtree/latin-500.css'
import '@fontsource/figtree/latin-600.css'
import '@fontsource/figtree/latin-700.css'
import '@fontsource/bricolage-grotesque/latin-500.css'
import '@fontsource/bricolage-grotesque/latin-700.css'
import '@fontsource/bricolage-grotesque/latin-800.css'
import './styles.css'
import App from './App.jsx'
import { migrateLegacyStorage } from './storage.js'

if (typeof localStorage !== 'undefined') migrateLegacyStorage(localStorage)   // before any page reads its keys
createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
