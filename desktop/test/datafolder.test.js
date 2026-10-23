// node --test desktop/test
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')
const {
  envVar, inspectFolder, migrateLegacyDataDir, migrateLegacyUserData, readConfig, resolveDataDir, writeConfig,
} = require('../datafolder.js')

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'dc-folder-'))

test('precedence: env var > app-config.json > default', () => {
  const cfg = tmp(), chosen = tmp(), envDir = tmp()
  const defaultDir = path.join(cfg, 'default')
  assert.deepEqual(resolveDataDir({ env: {}, configDir: cfg, defaultDir }), { dir: defaultDir, source: 'default' })
  writeConfig(cfg, { dataDir: chosen })
  assert.deepEqual(resolveDataDir({ env: {}, configDir: cfg, defaultDir }), { dir: chosen, source: 'config' })
  assert.deepEqual(resolveDataDir({ env: { DIMAAGI_DATA_DIR: envDir }, configDir: cfg, defaultDir }), { dir: envDir, source: 'env' })
})

test('a configured folder that no longer exists falls back to the default', () => {
  const cfg = tmp()
  writeConfig(cfg, { dataDir: path.join(cfg, 'gone') })
  assert.equal(resolveDataDir({ env: {}, configDir: cfg, defaultDir: 'D' }).source, 'default')
})

test('writeConfig with null removes the setting (back to the default)', () => {
  const cfg = tmp()
  writeConfig(cfg, { dataDir: 'C:\\x' })
  writeConfig(cfg, { dataDir: null })
  assert.deepEqual(readConfig(cfg), {})
})

test('an existing Dimaagi Cart folder is recognised, with a key in its .env', () => {
  const d = tmp()
  fs.mkdirSync(path.join(d, 'models'))
  fs.writeFileSync(path.join(d, 'models', 'segments.json'), '{}')
  fs.mkdirSync(path.join(d, 'stores'))
  fs.writeFileSync(path.join(d, '.env'), 'GEMINI_API_KEY=abc\n')
  const r = inspectFolder(d)
  assert.equal(r.ok, true)
  assert.equal(r.kind, 'existing')
  assert.deepEqual(r.found, ['segments', 'stores'])
  assert.equal(r.keyInEnv, true)
})

test('empty and new folders are accepted; a folder of other files is not', () => {
  const d = tmp()
  assert.equal(inspectFolder(d).kind, 'empty')
  assert.equal(inspectFolder(path.join(d, 'new-one')).kind, 'new')
  fs.writeFileSync(path.join(d, 'holiday.jpg'), 'x')
  const r = inspectFolder(d)
  assert.equal(r.ok, false)
  assert.match(r.message, /other files/)
})

test('relative paths, files, missing parents and the install folder are refused', () => {
  const d = tmp()
  fs.writeFileSync(path.join(d, 'a.txt'), 'x')
  assert.equal(inspectFolder('relative\\path').ok, false)
  assert.equal(inspectFolder(path.join(d, 'a.txt')).ok, false)
  assert.equal(inspectFolder(path.join(d, 'no', 'such', 'parent')).ok, false)
  assert.equal(inspectFolder(path.join(d, 'resources', 'x'), { forbidden: [d] }).ok, false)
})

// ---------- legacy migration (WinBack AI, up to v0.3.1) ----------
const write = (file, text) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, text) }
const read = (file) => fs.readFileSync(file, 'utf8')

test('env vars: DIMAAGI_ is used, the legacy WINBACK_ alias still works, DIMAAGI_ wins if both are set', () => {
  assert.equal(envVar({ DIMAAGI_DATA_DIR: 'new' }, 'DATA_DIR'), 'new')
  assert.equal(envVar({ WINBACK_DATA_DIR: 'old' }, 'DATA_DIR'), 'old')
  assert.equal(envVar({ DIMAAGI_DATA_DIR: 'new', WINBACK_DATA_DIR: 'old' }, 'DATA_DIR'), 'new')
  assert.equal(envVar({}, 'DATA_DIR'), undefined)
  const cfg = tmp(), oldDir = tmp(), newDir = tmp()
  assert.deepEqual(resolveDataDir({ env: { WINBACK_DATA_DIR: oldDir }, configDir: cfg, defaultDir: 'D' }), { dir: oldDir, source: 'env' })
  assert.deepEqual(resolveDataDir({ env: { WINBACK_DATA_DIR: oldDir, DIMAAGI_DATA_DIR: newDir }, configDir: cfg, defaultDir: 'D' }),
    { dir: newDir, source: 'env' })
})

test('data folder: the legacy folder is copied (not moved) when the new one is missing', async () => {
  const appData = tmp()
  const legacyDir = path.join(appData, 'WinBack'), newDir = path.join(appData, 'DimaagiCart')
  write(path.join(legacyDir, 'stores', 'corner', 'scored.csv'), 'id,risk\n1,0.9\n')
  write(path.join(legacyDir, 'settings.json'), '{"active_store":"corner"}')
  const res = await migrateLegacyDataDir({ legacyDir, newDir })
  assert.deepEqual(res, { from: legacyDir, to: newDir })
  assert.equal(read(path.join(newDir, 'stores', 'corner', 'scored.csv')), 'id,risk\n1,0.9\n')
  assert.equal(read(path.join(newDir, 'settings.json')), '{"active_store":"corner"}')
  // the legacy folder is untouched, and no temporary copy is left behind
  assert.equal(read(path.join(legacyDir, 'stores', 'corner', 'scored.csv')), 'id,risk\n1,0.9\n')
  assert.equal(fs.existsSync(`${newDir}.copying`), false)
  // a second launch does nothing
  assert.equal(await migrateLegacyDataDir({ legacyDir, newDir }), null)
})

test('data folder: never overwrites an existing new folder, never deletes the legacy one', async () => {
  const appData = tmp()
  const legacyDir = path.join(appData, 'WinBack'), newDir = path.join(appData, 'DimaagiCart')
  write(path.join(legacyDir, 'settings.json'), 'old')
  write(path.join(newDir, 'settings.json'), 'new')
  assert.equal(await migrateLegacyDataDir({ legacyDir, newDir }), null)
  assert.equal(read(path.join(newDir, 'settings.json')), 'new')
  assert.equal(read(path.join(legacyDir, 'settings.json')), 'old')
  assert.equal(await migrateLegacyDataDir({ legacyDir: path.join(appData, 'missing'), newDir: path.join(appData, 'x') }), null)
  assert.equal(fs.existsSync(path.join(appData, 'x')), false)
})

test('data folder: an interrupted earlier copy is redone, not kept', async () => {
  const appData = tmp()
  const legacyDir = path.join(appData, 'WinBack'), newDir = path.join(appData, 'DimaagiCart')
  write(path.join(legacyDir, 'models', 'segments.json'), '{"full":true}')
  write(path.join(`${newDir}.copying`, 'half-written.tmp'), 'x')
  await migrateLegacyDataDir({ legacyDir, newDir })
  assert.equal(read(path.join(newDir, 'models', 'segments.json')), '{"full":true}')
  assert.equal(fs.existsSync(path.join(newDir, 'half-written.tmp')), false)
})

test('app-config.json and localStorage: copied from the legacy Electron folder only where missing', () => {
  const appData = tmp()
  const legacyDir = path.join(appData, 'WinBack AI'), userData = path.join(appData, 'Dimaagi Cart')
  writeConfig(legacyDir, { dataDir: 'C:\Projects\shop', port: 51234 })
  write(path.join(legacyDir, 'Local Storage', 'leveldb', '000003.log'), 'ticks')
  assert.deepEqual(migrateLegacyUserData({ legacyDir, userData }), ['app-config.json', 'Local Storage'])
  assert.deepEqual(readConfig(userData), { dataDir: 'C:\Projects\shop', port: 51234 })
  assert.equal(read(path.join(userData, 'Local Storage', 'leveldb', '000003.log')), 'ticks')
  assert.deepEqual(readConfig(legacyDir), { dataDir: 'C:\Projects\shop', port: 51234 })     // legacy left as is
  // the new folder's own settings win from then on
  writeConfig(userData, { port: 6000 })
  assert.deepEqual(migrateLegacyUserData({ legacyDir, userData }), [])
  assert.equal(readConfig(userData).port, 6000)
  assert.deepEqual(migrateLegacyUserData({ legacyDir: path.join(appData, 'none'), userData }), [])
})
