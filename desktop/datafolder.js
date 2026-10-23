// Where Dimaagi Cart keeps its data, and whether a folder the owner picks can be used.
// Precedence: the DIMAAGI_DATA_DIR environment variable > app-config.json (chosen in Settings) > the default
// (%APPDATA%\DimaagiCart packaged, the repo in development). Pure functions, so they can be tested without Electron.
const fs = require('node:fs')
const path = require('node:path')

const CONFIG_FILE = 'app-config.json'
const ENV_PREFIX = 'DIMAAGI_'
// Before v0.3.2 the app was WinBack AI. Its env vars, data folder and Electron folder are still read (legacy migration).
const LEGACY = { productName: 'WinBack AI', envPrefix: 'WINBACK_', dataDirName: 'WinBack', userDataName: 'WinBack AI' }
// What Electron's own folder holds for the page: the chosen data folder and port, and localStorage (checklist ticks)
const USER_DATA_ITEMS = [CONFIG_FILE, 'Local Storage']
// Files that mark a folder as Dimaagi Cart's: shipped or generated data, owners' stores, settings, knowledge bases
const MARKERS = {
  segments: 'models/segments.json', model: 'models/churn_model.pkl', stores: 'stores',
  settings: 'settings.json', reviews_kb: 'data/vectorstore/chroma.sqlite3',
}

function readConfig(configDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(configDir, CONFIG_FILE), 'utf8'))
  } catch {
    return {}
  }
}

function writeConfig(configDir, updates) {
  const next = { ...readConfig(configDir), ...updates }
  for (const [k, v] of Object.entries(next)) if (v === null || v === undefined) delete next[k]
  fs.mkdirSync(configDir, { recursive: true })
  fs.writeFileSync(path.join(configDir, CONFIG_FILE), JSON.stringify(next, null, 2))
  return next
}

// DIMAAGI_<name>, else the deprecated legacy alias; DIMAAGI_ wins if both are set
function envVar(env, name) {
  return env[ENV_PREFIX + name] || env[LEGACY.envPrefix + name] || undefined
}

// -> { dir, source: 'env' | 'config' | 'default' }; a configured folder that has vanished falls back to the default
function resolveDataDir({ env = process.env, configDir, defaultDir }) {
  const fromEnv = envVar(env, 'DATA_DIR')
  if (fromEnv) return { dir: path.resolve(fromEnv), source: 'env' }
  const chosen = readConfig(configDir).dataDir
  if (chosen && fs.existsSync(chosen)) return { dir: path.resolve(chosen), source: 'config' }
  return { dir: defaultDir, source: 'default' }
}

function hasKeyInEnvFile(dir) {
  // Only whether a key is set: the value is never read into the app here
  try {
    return /^\s*GEMINI_API_KEY\s*=\s*\S+/m.test(fs.readFileSync(path.join(dir, '.env'), 'utf8'))
  } catch {
    return false
  }
}

function isInside(child, parent) {
  const rel = path.relative(parent, child)
  return rel === '' || (!!rel && !rel.startsWith('..') && !path.isAbsolute(rel))
}

// Can this folder hold Dimaagi Cart's data? -> { ok, kind: 'existing' | 'empty' | 'new', message, found, keyInEnv }
function inspectFolder(dir, { forbidden = [] } = {}) {
  const fail = (message) => ({ ok: false, kind: null, message })
  if (!dir || !path.isAbsolute(dir)) return fail('Choose a full folder path, e.g. C:\\Users\\you\\DimaagiCart.')
  const target = path.resolve(dir)
  if (forbidden.some((f) => f && isInside(target, path.resolve(f)))) {
    return fail("That's inside the app's own installation folder, which is replaced on every update.")
  }
  if (!fs.existsSync(target)) {
    const parent = path.dirname(target)
    if (!fs.existsSync(parent)) return fail(`The folder ${parent} doesn't exist.`)
    return { ok: true, kind: 'new', message: 'A new folder will be created and set up with the demo store.', found: [], keyInEnv: false }
  }
  if (!fs.statSync(target).isDirectory()) return fail('That is a file, not a folder.')
  try {
    const probe = path.join(target, `.dimaagi-write-test-${process.pid}`)
    fs.writeFileSync(probe, 'ok')
    fs.unlinkSync(probe)
  } catch {
    return fail("Dimaagi Cart can't write to this folder. Choose one in your user folder.")
  }
  const found = Object.entries(MARKERS).filter(([, rel]) => fs.existsSync(path.join(target, rel))).map(([k]) => k)
  const keyInEnv = hasKeyInEnvFile(target)
  if (found.length) {
    return { ok: true, kind: 'existing', found, keyInEnv,
      message: `An existing Dimaagi Cart folder${found.includes('stores') ? ' with your stores' : ''}${found.includes('reviews_kb') ? ' and knowledge bases' : ''}.` }
  }
  const entries = fs.readdirSync(target).filter((e) => !e.startsWith('.'))
  if (!entries.length) return { ok: true, kind: 'empty', message: 'An empty folder: Dimaagi Cart will set it up with the demo store.', found: [], keyInEnv }
  return fail("This folder has other files and doesn't look like a Dimaagi Cart folder. Choose an empty folder or an existing Dimaagi Cart folder.")
}

// ---------- legacy migration (the app was WinBack AI up to v0.3.1) ----------
// Copy app-config.json and localStorage from the legacy Electron folder (%APPDATA%\WinBack AI) into the new one,
// item by item, only where the new one has nothing yet. Never overwrites, never deletes. -> the items copied
function migrateLegacyUserData({ legacyDir, userData }) {
  const copied = []
  if (!legacyDir || path.resolve(legacyDir) === path.resolve(userData) || !fs.existsSync(legacyDir)) return copied
  for (const item of USER_DATA_ITEMS) {
    const from = path.join(legacyDir, item), to = path.join(userData, item)
    if (!fs.existsSync(from) || fs.existsSync(to)) continue
    fs.mkdirSync(userData, { recursive: true })
    fs.cpSync(from, to, { recursive: true, force: false, errorOnExist: false })
    copied.push(item)
  }
  return copied
}

// First launch after the rename: if the legacy default data folder exists and the new one doesn't, copy (not move)
// it over. Copies into a temporary sibling and renames it at the end, so an interrupted copy is redone next time
// instead of leaving half a folder. Never overwrites, never deletes the legacy folder. -> { from, to } or null
async function migrateLegacyDataDir({ legacyDir, newDir }) {
  if (!legacyDir || fs.existsSync(newDir) || !fs.existsSync(legacyDir)) return null
  if (path.resolve(legacyDir) === path.resolve(newDir)) return null
  const partial = `${newDir}.copying`
  await fs.promises.rm(partial, { recursive: true, force: true })      // only ever our own unfinished copy
  await fs.promises.cp(legacyDir, partial, { recursive: true, force: false, errorOnExist: false, preserveTimestamps: true })
  if (fs.existsSync(newDir)) return null                                 // something else created it meanwhile
  await fs.promises.rename(partial, newDir)
  return { from: path.resolve(legacyDir), to: path.resolve(newDir) }
}

module.exports = {
  CONFIG_FILE, MARKERS, LEGACY, readConfig, writeConfig, envVar, resolveDataDir, inspectFolder, hasKeyInEnvFile,
  migrateLegacyUserData, migrateLegacyDataDir,
}
