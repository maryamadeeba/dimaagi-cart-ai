// node --test frontend/test
import assert from 'node:assert/strict'
import test from 'node:test'
import { migrateLegacyStorage } from '../src/storage.js'

// A minimal stand-in for window.localStorage
function memoryStorage(items = {}) {
  const map = new Map(Object.entries(items))
  return {
    get length() { return map.size },
    key: (i) => [...map.keys()][i] ?? null,
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, String(v)) },
    removeItem: (k) => { map.delete(k) },
    dump: () => Object.fromEntries(map),
  }
}

test('legacy checklist ticks move to the new key names', () => {
  const s = memoryStorage({ 'winback.checklist.highvalue': '["a","b"]', 'winback.checklist.core': '["c"]', other: 'x' })
  assert.equal(migrateLegacyStorage(s), 2)
  assert.deepEqual(s.dump(), { 'dimaagi.checklist.highvalue': '["a","b"]', 'dimaagi.checklist.core': '["c"]', other: 'x' })
})

test('runs once: a second start changes nothing', () => {
  const s = memoryStorage({ 'winback.checklist.core': '["c"]' })
  migrateLegacyStorage(s)
  const after = s.dump()
  assert.equal(migrateLegacyStorage(s), 0)
  assert.deepEqual(s.dump(), after)
})

test('a value already saved under the new name is kept', () => {
  const s = memoryStorage({ 'winback.checklist.core': '["old"]', 'dimaagi.checklist.core': '["new"]' })
  assert.equal(migrateLegacyStorage(s), 0)
  assert.deepEqual(s.dump(), { 'dimaagi.checklist.core': '["new"]' })
})

test('unavailable storage is ignored', () => {
  const broken = { get length() { throw new Error('SecurityError') } }
  assert.equal(migrateLegacyStorage(broken), 0)
})
