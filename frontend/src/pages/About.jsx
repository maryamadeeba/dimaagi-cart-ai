import { useApp } from '../state.jsx'

const SOURCES = [
  { name: 'Demo store: dunnhumby The Complete Journey', note: 'Used for research and education. Real, anonymised grocery data (2017); the app ships its churn models, segments and customer scores, keyed by anonymised household numbers.' },
  { name: 'Grocery reviews: Yelp Open Dataset', note: 'Used under Yelp\'s dataset terms. Not included in the app: you build the reviews knowledge base on this computer from your own download.' },
  { name: 'Marketing reports', note: 'Listrak, Klaviyo, Merkle, Bond Brand Loyalty, Optimove, Sprout Social, Hootsuite, McKinsey & EuroCommerce, Deloitte, FMI and MailGenius. Cited by page; not included in the app.' },
  { name: 'AI', note: 'Google Gemini writes the reasons, campaign kits and chat answers with your own API key. Embeddings and reranking run locally (BGE-small, MiniLM).' },
  { name: 'Fonts', note: 'Bricolage Grotesque and Figtree, SIL Open Font License 1.1, bundled with the app.' },
]

export default function About() {
  const { health } = useApp()
  return (
    <div className="page" style={{ gap: 22 }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="eyebrow">About</span>
        <h1 className="h1">Dimaagi Cart{health?.version ? ` ${health.version}` : ''}</h1>
        <p className="lead">Your store's smart cart: spot drifting regulars, see why, and win them back. By Maryam Adeeba. Open source (MIT).</p>
        <p style={{ margin: 0, fontSize: 15, color: 'var(--muted)' }}>“Dimaagi” is Urdu for smart, brainy.</p>
      </header>
      <section className="card" aria-labelledby="about-data" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <h2 id="about-data" className="h2 sm">Data and credits</h2>
        <dl style={{ margin: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {SOURCES.map((s) => (
            <div key={s.name}>
              <dt style={{ fontWeight: 700 }}>{s.name}</dt>
              <dd style={{ margin: '2px 0 0', fontSize: 15, lineHeight: 1.5, color: 'var(--body)' }}>{s.note}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="card" aria-labelledby="about-privacy" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <h2 id="about-privacy" className="h2 sm">Your data</h2>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55 }}>
          Your sales data, scores and knowledge bases stay on this computer{health?.data_dir ? <> in <code>{health.data_dir}</code></> : ''}.
          Your Gemini key is kept in Windows Credential Manager. Only short review snippets and segment numbers are sent to Gemini
          when you write reasons, kits or chat answers.
        </p>
      </section>
    </div>
  )
}
