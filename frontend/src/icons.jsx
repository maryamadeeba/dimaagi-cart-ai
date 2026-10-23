// Inline stroke icons copied from the design files.
const stroke = { fill: 'none', stroke: 'currentColor', strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }

export function LogoMark({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 34 34" aria-hidden="true">
      <rect width="34" height="34" rx="10" fill="#E0582B" />
      <path d="M10 19c0-5 4-9 9-9h3m0 0-3-3m3 3-3 3M24 15c0 5-4 9-9 9h-3m0 0 3 3m-3-3 3-3" fill="none" stroke="#FBF7EF"
        strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function AvatarMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 34 34" aria-hidden="true">
      <path d="M10 19c0-5 4-9 9-9h3m0 0-3-3m3 3-3 3M24 15c0 5-4 9-9 9h-3m0 0 3 3m-3-3 3-3" fill="none" stroke="#FBF7EF"
        strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export const Icon = {
  dashboard: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...stroke}>
      <rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" />
      <rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" />
    </svg>
  ),
  users: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...stroke}>
      <circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.2a6.5 6.5 0 0 1 3.5 5.8" />
    </svg>
  ),
  search: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...stroke}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
  ),
  message: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...stroke}><path d="M4 4h16v12H5l-1 4z" /><path d="M8 9h8M8 12h5" /></svg>
  ),
  star: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...stroke}>
      <path d="M12 3l2.2 5.3L20 9l-4.4 3.8L17 18.5 12 15.6 7 18.5l1.4-5.7L4 9l5.8-.7z" />
    </svg>
  ),
  retrain: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...stroke}><path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5" /></svg>
  ),
  arrow: ({ size = 18, width = 2.2 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" strokeWidth={width} {...stroke}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
  ),
  info: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" stroke="#2F6B4F" strokeWidth="2" fill="none" strokeLinecap="round"
      style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
  ),
  warning: ({ color = '#1F3B2D' }) => (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true"><path d="M12 3 2 20h20z" /><path d="M12 10v4M12 17h.01" /></svg>
  ),
  check: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" strokeWidth="3" {...stroke}><path d="m5 12 5 5L20 7" /></svg>
  ),
  cross: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" strokeWidth="3" {...stroke}><path d="M6 6l12 12M18 6 6 18" /></svg>
  ),
  download: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" strokeWidth="2" {...stroke}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>
  ),
  gift: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E0582B" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true">
      <path d="M20 12v8H4v-8M2 7h20v5H2zM12 20V7M12 7H8a2 2 0 1 1 2-3l2 3 2-3a2 2 0 1 1 2 3z" />
    </svg>
  ),
  photo: () => (
    <svg width="32" height="32" viewBox="0 0 24 24" strokeWidth="1.8" {...stroke}>
      <rect x="3" y="5" width="18" height="14" rx="3" /><circle cx="9" cy="11" r="2" /><path d="m21 16-5-5-8 8" />
    </svg>
  ),
  upload: () => (
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#2F6B4F" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M4 20h16" /></svg>
  ),
  lock: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2F6B4F" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true">
      <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  ),
  send: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2.4" {...stroke}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
  ),
  spinner: () => (
    <svg className="spin" width="16" height="16" viewBox="0 0 24 24" strokeWidth="3" {...stroke}><path d="M12 3a9 9 0 1 0 9 9" /></svg>
  ),
}
