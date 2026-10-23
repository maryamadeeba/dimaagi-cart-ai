import { Link } from 'react-router-dom'
import ModelCard from '../components/ModelCard.jsx'
import SetupCard from '../components/SetupCard.jsx'
import { useApp } from '../state.jsx'

export default function Model() {
  const { dashError } = useApp()
  return (
    <div className="page" style={{ gap: 22 }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="eyebrow">About this model</span>
        <h1 className="h1">How the risk scores are made</h1>
        <p className="lead">A machine-learning model trained on shopping history, tested on a later period it never saw. <Link to="/customers">See each customer's score</Link>.</p>
      </header>
      {dashError?.code === 'missing_output' ? <SetupCard title="No model yet" message={dashError.message} showKbs={false} /> : <ModelCard />}
    </div>
  )
}
