export const money0 = (v) => `$${Math.round(v ?? 0).toLocaleString('en-US')}`
export const money2 = (v) => `$${(v ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export const moneyShort = (v) => (Number.isInteger(v) ? `$${v}` : money2(v))
export const pct0 = (share) => `${Math.round((share ?? 0) * 100)}%`
export const pct1 = (share) => `${((share ?? 0) * 100).toFixed(1)}%`
export const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)

// "High-value · at risk" -> "High-value"; core segment names stay as they are
export const shortName = (name) => name.replace(/\s*·\s*at risk$/i, '')

export function niceDate(iso) {
  if (!iso) return ''
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Segments in the design's order: the focus segment first, then by revenue at risk
export function orderSegments(segments, focus) {
  return [...segments].sort((a, b) =>
    (b.slug === focus) - (a.slug === focus) || b.weekly_revenue_at_risk - a.weekly_revenue_at_risk)
}

export const tabLabel = (s) => `${shortName(s.name)} · ${s.customers}`
