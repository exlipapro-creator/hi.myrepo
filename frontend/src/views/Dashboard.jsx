import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, CheckCircle, Clock, Zap } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

export default function Dashboard() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [incidents, setIncidents] = useState([])
  const [events, setEvents] = useState([])
  const [providers, setProviders] = useState([])
  const [runbooks, setRunbooks] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [projRes, incRes, evRes, provRes, rbRes] = await Promise.allSettled([
        fetch(`${API}/projects`, { headers: authHeaders() }),
        fetch(`${API}/incidents?limit=10`, { headers: authHeaders() }),
        fetch(`${API}/events?limit=20`, { headers: authHeaders() }),
        fetch(apiUrl('/v1/providers'), { headers: authHeaders() }),
        fetch(`${API}/runbooks`, { headers: authHeaders() }),
      ])

      if (projRes.status === 'fulfilled' && projRes.value.ok) {
        setProjects(await projRes.value.json())
      }
      if (incRes.status === 'fulfilled' && incRes.value.ok) {
        setIncidents(await incRes.value.json())
      }
      if (evRes.status === 'fulfilled' && evRes.value.ok) {
        const data = await evRes.value.json()
        setEvents(data.events || [])
      }
      if (provRes.status === 'fulfilled' && provRes.value.ok) {
        setProviders(await provRes.value.json())
      }
      if (rbRes.status === 'fulfilled' && rbRes.value.ok) {
        setRunbooks(await rbRes.value.json())
      }
    } catch (e) {
      console.error('Failed to load dashboard:', e)
    } finally {
      setLoading(false)
    }
  }

  function authHeaders() {
    const token = localStorage.getItem('token')
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  const activeIncidents = Array.isArray(incidents) ? incidents.filter(i => i.status !== 'RESOLVED') : []
  const criticalCount = activeIncidents.filter(i => i.severity === 'critical').length
  const healthyProviders = providers.filter(p => p.status === 'healthy').length

  // ── Bootstrap: Empty state for new organizations ──────────────────
  if (!loading && projects.length === 0) {
    return (
      <div>
        <div className="page-header">
          <h1>hi.myrepo // COMMAND CENTER</h1>
          <span className="mono" style={{ color: 'var(--text-muted)' }}>
            {new Date().toLocaleTimeString()}
          </span>
        </div>

        {/* Welcome Banner */}
        <div className="card" style={{
          marginBottom: 'var(--space-lg)',
          background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0, rgba(139, 92, 246, 0.08) 100%)',
          border: '1px solid rgba(59, 130, 246, 0.2)',
        }}>
          <div style={{ textAlign: 'center', padding: 'var(--space-lg)' }}>
            <div style={{ fontSize: '32px', marginBottom: 'var(--space-md)' }}>🎯</div>
            <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: 'var(--space-sm)' }}>
              Welcome to hi.myrepo
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', maxWidth: '500px', margin: '0 auto var(--space-lg)' }}>
              Your control plane is ready. Connect your first system to begin observing,
              understanding, and responding to incidents with AI-augmented intelligence.
            </p>
            <div style={{ display: 'flex', gap: 'var(--space-sm)', justifyContent: 'center' }}>
              <button
                className="btn btn-primary"
                onClick={() => navigate('/projects')}
                style={{ fontSize: '14px' }}
              >
                + Create Your First Project
              </button>
            </div>
          </div>
        </div>

        {/* System Overview */}
        <div className="bento-grid" style={{ marginBottom: 'var(--space-md)' }}>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">Projects</div>
            <div className="metric-value">0</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>Create one to start</div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">Events</div>
            <div className="metric-value">{events.length}</div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">Incidents</div>
            <div className="metric-value">{activeIncidents.length}</div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">AI Providers</div>
            <div className="metric-value" style={{ color: healthyProviders > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
              {healthyProviders}
              <span style={{ fontSize: '12px', fontWeight: 400 }}> healthy</span>
            </div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">Runbooks</div>
            <div className="metric-value">{runbooks.length}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>available</div>
          </div>
        </div>

        {/* How it works */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">HOW IT WORKS</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-md)', padding: 'var(--space-sm)' }}>
            {[
              { icon: '📡', title: 'Observe', desc: 'Ingest events, heartbeats, and telemetry from your systems' },
              { icon: '🤖', title: 'Understand', desc: 'AI analyzes patterns, correlates events, and identifies root causes' },
              { icon: '📋', title: 'Act', desc: 'Propose and approve runbook executions for remediation' },
              { icon: '🔄', title: 'Autonomy', desc: 'Progressively grant the system more authority as trust builds' },
            ].map((step, i) => (
              <div key={i} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '24px', marginBottom: 'var(--space-sm)' }}>{step.icon}</div>
                <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>{step.title}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{step.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // ── Normal dashboard with data ────────────────────────────────────
  return (
    <div>
      <div className="page-header">
        <h1>hi.myrepo // COMMAND CENTER</h1>
        <span className="mono" style={{ color: 'var(--text-muted)' }}>
          {new Date().toLocaleTimeString()}
        </span>
      </div>

      {/* ── Summary Metrics ─────────────────────────────────────────── */}
      <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="card-title">Projects</div>
          <div className="metric-value">{projects.length}</div>
        </div>
        <div className="card">
          <div className="card-title">Active Incidents</div>
          <div className="metric-value" style={{ color: activeIncidents.length > 0 ? 'var(--accent-orange)' : 'var(--accent-green)' }}>
            {activeIncidents.length}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Critical</div>
          <div className="metric-value" style={{ color: criticalCount > 0 ? 'var(--accent-red)' : 'var(--text-muted)' }}>
            {criticalCount}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Recent Events</div>
          <div className="metric-value">{events.length}</div>
        </div>
      </div>

      {/* ── Projects + Event Spine ──────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-md)' }}>
        {/* Projects */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">PROJECTS</span>
            <button
              className="btn"
              onClick={() => navigate('/projects')}
              style={{ fontSize: '11px', padding: '2px 8px', color: 'var(--accent-blue)' }}
            >
              View All →
            </button>
          </div>
          {projects.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', padding: 'var(--space-md)', textAlign: 'center' }}>
              {loading ? 'Loading...' : 'No projects yet'}
            </div>
          ) : (
            <div className="bento-grid" style={{ gridTemplateColumns: '1fr' }}>
              {projects.slice(0, 5).map(p => (
                <div
                  key={p.id}
                  onClick={() => navigate('/projects')}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: 'var(--space-sm)', borderRadius: 'var(--radius-sm)',
                    background: 'var(--bg-secondary)', cursor: 'pointer',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>{p.name}</div>
                    <div className="mono" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{p.slug}</div>
                  </div>
                  <span className="status-badge healthy">
                    <span className="status-dot healthy"></span>
                    {p.is_active ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Real-Time Event Spine */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">REAL-TIME EVENT SPINE</span>
          </div>
          <div className="event-stream">
            {events.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', padding: 'var(--space-md)', textAlign: 'center' }}>
                {loading ? 'Loading...' : 'No events yet'}
              </div>
            ) : (
              events.map(e => (
                <div key={e.id} className="event-item">
                  <span className="event-type">{e.event_type}</span>
                  <span className="event-source">{e.source}</span>
                  <span className="event-time">
                    {e.received_at ? formatDistanceToNow(new Date(e.received_at), { addSuffix: true }) : ''}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* ── Active Incidents ────────────────────────────────────────── */}
      {activeIncidents.length > 0 && (
        <div className="card" style={{ marginTop: 'var(--space-md)' }}>
          <div className="card-header">
            <span className="card-title">ACTIVE INCIDENTS</span>
            <button
              className="btn"
              onClick={() => navigate('/incidents')}
              style={{ fontSize: '11px', padding: '2px 8px', color: 'var(--accent-blue)' }}
            >
              View All →
            </button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Severity</th>
                <th>Status</th>
                <th>Title</th>
                <th>Service</th>
                <th>Confidence</th>
                <th>Detected</th>
              </tr>
            </thead>
            <tbody>
              {activeIncidents.map(inc => (
                <tr key={inc.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/incidents/${inc.id}`)}>
                  <td><span className={`severity-badge ${inc.severity}`}>{inc.severity}</span></td>
                  <td className="mono" style={{ fontSize: '12px' }}>{inc.status}</td>
                  <td>{inc.title || inc.fingerprint || 'Unknown'}</td>
                  <td className="mono" style={{ fontSize: '12px' }}>{inc.affected_service || '—'}</td>
                  <td className="mono">{inc.confidence != null ? `${(inc.confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {inc.detected_at ? formatDistanceToNow(new Date(inc.detected_at), { addSuffix: true }) : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
