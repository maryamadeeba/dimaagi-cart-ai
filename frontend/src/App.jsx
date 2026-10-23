import { HashRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar.jsx'
import { AppProvider, useApp } from './state.jsx'
import About from './pages/About.jsx'
import Ask from './pages/Ask.jsx'
import Customers from './pages/Customers.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Import from './pages/Import.jsx'
import Model from './pages/Model.jsx'
import Retrain from './pages/Retrain.jsx'
import Welcome from './pages/Welcome.jsx'
import Why from './pages/Why.jsx'
import WinThemBack from './pages/WinThemBack.jsx'

function DemoBanner() {
  const { health } = useApp()
  if (health?.app?.active_store !== 'demo') return null
  return (
    <div className="demo-banner" role="note">
      <span><strong>{health.app.demo_label}</strong></span>
      <Link to="/import">Connect my sales data</Link>
    </div>
  )
}

function Shell() {
  const { health } = useApp()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  // First launch: choose demo or own data. The import wizard stays reachable from the welcome screen.
  if (health && !health.error && !health.app?.mode && pathname !== '/import') {
    return <Welcome onConnect={() => navigate('/import')} />
  }
  return (
    <>
      <button type="button" className="skip" onClick={() => document.getElementById('main')?.focus()}>Skip to content</button>
      <div className="shell">
        <Sidebar />
        <main className="main" id="main" tabIndex={-1}>
          <DemoBanner />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/why/:slug?" element={<Why />} />
            <Route path="/win-back/:slug?" element={<WinThemBack />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/retrain" element={<Retrain />} />
            <Route path="/import" element={<Import />} />
            <Route path="/model" element={<Model />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </>
  )
}

// Hash routes work the same whether the page comes from Vite, the backend or a file.
export default function App() {
  return (
    <AppProvider>
      <HashRouter>
        <Shell />
      </HashRouter>
    </AppProvider>
  )
}
