// localStorage keys moved from the legacy 'winback.' prefix (the app was WinBack AI up to v0.3.1) to 'dimaagi.'.
// Runs once at startup: each legacy key is copied where the new key isn't set yet, then removed, so it runs once.
export const PREFIX = 'dimaagi.'
const LEGACY_PREFIX = 'winback.'

export function migrateLegacyStorage(storage) {
  let moved = 0
  try {
    const legacyKeys = []
    for (let i = 0; i < storage.length; i += 1) {
      const k = storage.key(i)
      if (k?.startsWith(LEGACY_PREFIX)) legacyKeys.push(k)
    }
    for (const k of legacyKeys) {
      const next = PREFIX + k.slice(LEGACY_PREFIX.length)
      if (storage.getItem(next) === null) {
        storage.setItem(next, storage.getItem(k))
        moved += 1
      }
      storage.removeItem(k)
    }
  } catch { /* storage unavailable: nothing to migrate */ }
  return moved
}
