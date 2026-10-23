// Dimaagi Cart desktop shell: starts the local backend on a free port with a one-time token, shows a splash
// until /api/health answers, then opens the app. The backend is stopped when the app quits.
const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron')
const { spawn, execFileSync } = require('node:child_process')
const crypto = require('node:crypto')
const fs = require('node:fs')
const net = require('node:net')
const path = require('node:path')
const {
  LEGACY, envVar, inspectFolder, migrateLegacyDataDir, migrateLegacyUserData, readConfig, resolveDataDir, writeConfig,
} = require('./datafolder.js')

const DEV_URL = 'http://localhost:5173'
const REPO = path.resolve(__dirname, '..')
const HEALTH_TIMEOUT_MS = 120_000          // first start imports the ML stack; slow disks need time
const ICON = path.join(__dirname, 'build', 'icon.png')

// DIMAAGI_DEV=1 or --dimaagi-dev: Vite dev server + Python backend (npm run dev)
// unpackaged without DIMAAGI_DEV: built front end served by the Python backend (npm start)
// packaged: the PyInstaller backend and front end from resources/
const devServer = envVar(process.env, 'DEV') === '1' || process.argv.includes('--dimaagi-dev')
const token = crypto.randomBytes(32).toString('base64url')
let port = 0
let backend = null
let backendLog = ''
let quitting = false
let mainWindow = null
let splash = null
let backendExited = Promise.resolve()
let restarting = false

const appUrl = () => (devServer ? DEV_URL : `http://127.0.0.1:${port}`)
// Launch tests only: DIMAAGI_APPDATA_DIR stands in for %APPDATA%, so a throwaway profile never touches the real one
if (process.env.DIMAAGI_APPDATA_DIR) {
  app.setPath('appData', path.resolve(process.env.DIMAAGI_APPDATA_DIR))
  app.setPath('userData', path.join(app.getPath('appData'), app.getName()))
}
// The data folder: DIMAAGI_DATA_DIR > app-config.json (Settings) > default. app-config.json lives in Electron's
// own folder (%APPDATA%\Dimaagi Cart), since the data folder can't record where it is itself.
const defaultDataDir = () => (app.isPackaged ? path.join(app.getPath('appData'), 'DimaagiCart') : REPO)
let legacyFallback = null                // set only if copying the legacy data folder failed (this session uses it)
const dataDir = () => (legacyFallback ? { dir: legacyFallback, source: 'default' }
  : resolveDataDir({ configDir: app.getPath('userData'), defaultDir: defaultDataDir() }))

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.unref()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const { port: p } = srv.address()
      srv.close(() => resolve(p))
    })
  })
}

function portIsFree(p) {
  return new Promise((resolve) => {
    const srv = net.createServer()
    srv.unref()
    srv.once('error', () => resolve(false))
    srv.listen(p, '127.0.0.1', () => srv.close(() => resolve(true)))
  })
}

// Reuse the same port whenever it's free: the page's origin (http://127.0.0.1:<port>) then stays the same, so what
// the page keeps in localStorage (checklist ticks) survives restarts. Only falls back to a new port if it's taken.
async function pickPort(preferred) {
  if (preferred && await portIsFree(preferred)) return preferred
  const p = await freePort()
  writeConfig(app.getPath('userData'), { port: p })
  return p
}

function pythonExe() {
  const venv = path.join(REPO, '.venv', 'Scripts', 'python.exe')
  return envVar(process.env, 'PYTHON') || (fs.existsSync(venv) ? venv : 'python')
}

function backendCommand() {
  const args = ['--port', String(port)]
  if (app.isPackaged) {
    const dir = path.join(process.resourcesPath, 'backend')
    return { cmd: path.join(dir, 'dimaagi-backend.exe'), args: [...args, '--static', path.join(process.resourcesPath, 'frontend')], cwd: dir }
  }
  if (devServer) return { cmd: pythonExe(), args: ['-m', 'src.api.app', ...args, '--dev'], cwd: REPO }
  return { cmd: pythonExe(), args: ['-m', 'src.api.app', ...args, '--static', path.join(REPO, 'frontend', 'dist')], cwd: REPO }
}

function startBackend() {
  const { cmd, args, cwd } = backendCommand()
  // The token goes through the environment, not argv, so it doesn't show in process listings.
  const env = { ...process.env, DIMAAGI_TOKEN: token, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1',
    DIMAAGI_DATA_DIR: dataDir().dir }
  backend = spawn(cmd, args, { cwd, env, windowsHide: true })
  const keep = (chunk) => { backendLog = (backendLog + chunk.toString()).slice(-8000) }
  backend.stdout.on('data', keep)
  backend.stderr.on('data', keep)
  backendExited = new Promise((resolve) => {
    backend.on('exit', (code) => resolve(code))
    backend.on('error', (err) => { keep(`\n${err.message}`); resolve(-1) })   // e.g. the exe is missing
  })
  backendExited.then((code) => {
    if (!quitting && !restarting && mainWindow) {
      dialog.showErrorBox('Dimaagi Cart', `The Dimaagi Cart engine stopped unexpectedly (exit code ${code}). Please restart the app.`)
    }
  })
  return backendExited
}

// Switch data folders without restarting the app: stop the engine, start it on the new folder, reload the page.
async function restartBackend(afterStart) {
  restarting = true
  try {
    stopBackend()
    await backendExited
    port = await pickPort(port)
    const ok = await waitForHealth(startBackend())
    if (ok && afterStart) await afterStart()
    if (ok) await mainWindow?.loadURL(appUrl())
    return ok
  } finally {
    restarting = false
  }
}

async function api(pathname, body) {
  const res = await fetch(`http://127.0.0.1:${port}/api${pathname}`, {
    method: body ? 'POST' : 'GET', headers: { 'X-Dimaagi-Token': token, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  return res.json()
}

function stopBackend() {
  if (!backend || backend.exitCode !== null) return
  try {
    // /T also ends children (the venv python.exe launcher starts the real interpreter as a child)
    execFileSync('taskkill', ['/pid', String(backend.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true })
  } catch {
    backend.kill()
  }
}

async function waitForHealth(exited) {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS
  let gone = false
  exited.then(() => { gone = true })
  while (Date.now() < deadline && !gone) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/health`, { headers: { 'X-Dimaagi-Token': token } })
      if (res.ok) return true
    } catch { /* not listening yet */ }
    await new Promise((r) => setTimeout(r, 400))
  }
  return false
}

function showSplash() {
  splash = new BrowserWindow({
    width: 440, height: 300, frame: false, resizable: false, center: true, show: false, backgroundColor: '#1F3B2D',
    icon: ICON, webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  splash.loadFile(path.join(__dirname, 'splash.html'))
  splash.once('ready-to-show', () => splash.show())
}

function showError(message) {
  splash?.destroy()
  const detail = backendLog.trim().split('\n').slice(-15).join('\n')
  dialog.showMessageBoxSync({
    type: 'error', title: 'Dimaagi Cart', buttons: ['Quit'],
    message: "Dimaagi Cart couldn't start its engine.",
    detail: `${message}\n\n${detail ? `Last messages from the engine:\n${detail}` : ''}`.trim(),
  })
  app.quit()
}

// ---------- legacy migration: the app was WinBack AI up to v0.3.1 ----------
// Electron's own folder is named after the app, so the chosen data folder, port and localStorage are copied from
// %APPDATA%\WinBack AI before anything opens them. The legacy folder is left as it is.
try {
  migrateLegacyUserData({ legacyDir: path.join(app.getPath('appData'), LEGACY.userDataName), userData: app.getPath('userData') })
} catch (err) {
  console.error(`Couldn't copy settings from the legacy app folder: ${err.message}`)    // starts with defaults instead
}

// The default data folder: copy the legacy %APPDATA%\WinBack to %APPDATA%\DimaagiCart once (if the new one doesn't exist)
async function migrateDataFolder() {
  const { dir, source } = dataDir()
  if (!app.isPackaged || source !== 'default') return
  const legacyDir = path.join(app.getPath('appData'), LEGACY.dataDirName)
  try {
    const copied = await migrateLegacyDataDir({ legacyDir, newDir: dir })
    if (copied) writeConfig(app.getPath('userData'), { legacyCopy: { ...copied, at: new Date().toISOString() } })
  } catch (err) {
    // Don't start a fresh, empty folder (that would stop the copy being retried): use the legacy one this time
    backendLog += `\nCouldn't copy ${legacyDir} to ${dir}: ${err.message}. Using ${legacyDir} for now.`
    legacyFallback = legacyDir
  }
}

// Shown once, after the copy: says where the data went and that the legacy install can go
function showLegacyNotice() {
  const cfg = readConfig(app.getPath('userData'))
  if (!cfg.legacyCopy || cfg.legacyNoticeShown) return
  writeConfig(app.getPath('userData'), { legacyNoticeShown: true })
  dialog.showMessageBox(mainWindow, {
    type: 'info', title: 'Dimaagi Cart', buttons: ['OK'],
    message: `${LEGACY.productName} is now Dimaagi Cart`,
    detail: `Your stores, scores and settings were copied to ${cfg.legacyCopy.to}.\n\n` +
      `The old folder ${cfg.legacyCopy.from} was left as it is; delete it once you're happy everything is here. ` +
      `If ${LEGACY.productName} 0.3.x is still installed, uninstall it from Settings → Apps.`,
  })
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440, height: 960, minWidth: 1024, minHeight: 700, title: 'Dimaagi Cart', show: false,
    backgroundColor: '#FBF7EF', icon: ICON, autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  mainWindow.removeMenu()
  // Keep the app on its own pages; real links (if any) open in the browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !url.startsWith(appUrl())) shell.openExternal(url)
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(appUrl())) e.preventDefault() })
  mainWindow.on('page-title-updated', (e) => e.preventDefault())
  mainWindow.once('ready-to-show', () => {
    splash?.destroy()
    splash = null
    mainWindow.show()
    showLegacyNotice()
  })
  mainWindow.loadURL(appUrl())

  // Smoke test: DIMAAGI_SCREENSHOT=out.png saves the first screen once data has loaded, then quits
  const screenshot = envVar(process.env, 'SCREENSHOT')
  if (screenshot) {
    mainWindow.webContents.once('did-finish-load', () => setTimeout(async () => {
      fs.writeFileSync(screenshot, (await mainWindow.webContents.capturePage()).toPNG())
      app.quit()
    }, 5000))
  }
}

ipcMain.on('dimaagi:config', (e) => { e.returnValue = { port, token } })
ipcMain.handle('dimaagi:pick-folder', async () => {
  const res = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory', 'createDirectory'] })
  return res.canceled ? null : res.filePaths[0]
})
// Data folder settings (Retrain screen and the welcome screen)
const installDirs = () => (app.isPackaged ? [path.dirname(process.execPath)] : [])
ipcMain.handle('dimaagi:data-folder', () => ({ ...dataDir(), defaultDir: defaultDataDir() }))
ipcMain.handle('dimaagi:check-folder', (_e, dir) => inspectFolder(dir, { forbidden: installDirs() }))
ipcMain.handle('dimaagi:set-data-folder', async (_e, dir, opts = {}) => {
  if (dataDir().source === 'env') {
    return { ok: false, message: 'The DIMAAGI_DATA_DIR environment variable sets the folder. Change or remove it there.' }
  }
  if (dir) {
    const check = inspectFolder(dir, { forbidden: installDirs() })
    if (!check.ok) return check
    fs.mkdirSync(dir, { recursive: true })
  }
  writeConfig(app.getPath('userData'), { dataDir: dir || null })      // null = back to the default
  legacyFallback = null
  // From the welcome screen ("Open an existing Dimaagi Cart folder"): that choice answers the welcome question, so the
  // reopened app goes straight to the folder's store instead of asking again.
  const finishWelcome = opts.fromWelcome ? async () => {
    const h = await api('/health')
    if (!h.app?.mode) await api('/stores/activate', { slug: h.app?.active_store || 'demo' })
  } : null
  const ok = await restartBackend(finishWelcome)
  if (!ok) showError(`The engine didn't start with the folder ${dataDir().dir}.`)
  return { ok }
})

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus() }
  })

  app.whenReady().then(async () => {
    showSplash()
    await migrateDataFolder()
    port = await pickPort(readConfig(app.getPath('userData')).port)
    const exited = startBackend()
    if (await waitForHealth(exited)) createMainWindow()
    else showError(backend?.exitCode !== null ? `The engine exited (code ${backend?.exitCode}).` : 'The engine did not answer in time.')
  })

  app.on('before-quit', () => { quitting = true; stopBackend() })
  app.on('window-all-closed', () => app.quit())
  process.on('exit', stopBackend)
}
