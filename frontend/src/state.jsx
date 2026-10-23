import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api } from './api.js'

// App-wide state: backend health, the dashboard (segments + model), background jobs and the chat.
const AppContext = createContext(null)
export const useApp = () => useContext(AppContext)

export function AppProvider({ children }) {
  const [health, setHealth] = useState(null)
  const [dashboard, setDashboard] = useState(null)
  const [dashError, setDashError] = useState(null)
  const [jobs, setJobs] = useState({})           // kind -> latest job
  const [chat, setChat] = useState(() => ({ id: crypto.randomUUID(), messages: [] }))
  const [version, setVersion] = useState(0)      // bumps when outputs change, so pages refetch
  const timers = useRef({})

  const refresh = useCallback(async () => {
    try { setHealth(await api.health()) } catch (e) { setHealth({ error: e }) }
    try { setDashboard(await api.dashboard()); setDashError(null) } catch (e) { setDashboard(null); setDashError(e) }
    setVersion((v) => v + 1)
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const track = useCallback((job) => {
    setJobs((j) => ({ ...j, [job.kind]: job }))
    clearInterval(timers.current[job.kind])
    if (job.status !== 'running') return
    timers.current[job.kind] = setInterval(async () => {
      try {
        const next = await api.job(job.id)
        setJobs((j) => ({ ...j, [next.kind]: next }))
        if (next.status !== 'running') {
          clearInterval(timers.current[next.kind])
          refresh()
        }
      } catch {
        clearInterval(timers.current[job.kind])
      }
    }, 1000)
  }, [refresh])

  useEffect(() => () => Object.values(timers.current).forEach(clearInterval), [])

  const busy = Object.values(jobs).some((j) => j.status === 'running')
  const newChat = () => setChat({ id: crypto.randomUUID(), messages: [] })

  return (
    <AppContext.Provider value={{ health, dashboard, dashError, refresh, version, jobs, track, busy, chat, setChat, newChat }}>
      {children}
    </AppContext.Provider>
  )
}
