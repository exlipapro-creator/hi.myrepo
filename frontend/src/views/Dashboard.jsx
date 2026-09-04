import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, CheckCircle, Clock, Zap, Eye, Brain, Play, RefreshCw, Shield } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const healthColors = {
  healthy: 'var(--accent-green)',
  degraded: 'var(--accent-orange)',
  unhealthy: 'var(--accent-red)',
  unknown: 'var(--text-muted)',
  no_targets: 'var(--text-muted)',
  stopped: 'var(--text-secondary)',
}

const healthLabels = {
  healthy: 'HEALTHY',
  degraded: 'DEGRADED',
  unhealthy: 'UNHEALTHY',
  unknown: 'UNKNOWN',
  no_targets: 'NO TARGETS',
  stopped: 'STOPPED',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [projectHealth, setProjectHealth] = useState({})
  const [incidents, setIncidents] = useState([])
  const [events, setEvents] = useState([])
  const [providers, setProviders] = useState([])
  const [runbooks, setRunbooks] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadData() }, [])

  async function loadData() {
    try {
      const [projRes, incRes, evRes, provRes, rbRes] = await Promise.allSettled([
        fetch(`${API}/projects`, { headers: authHeaders() }),
        fetch(`${API}/incidents?limit=10`, { headers: authHeaders() }),
        fetch(`${API}/events?limit=20`, { headers: authHeaders() }),
        fetch(`${API}/providers`, { headers: authHeaders() }),
        fetch(`${API}/runbooks`, { headers: authHeaders() }),
      ])

      if (projRes.status === 'fulfilled' && projRes.value.ok) {
        const projData = await projRes.value.json()
        setProjects(projData)
        // Fetch health for each project
        for (const p of projData) {
          try {
            const hRes = await fetch(`${API}/projects/${p.id}/health`, { headers: authHeaders() })
            if (hRes.ok) {
              const hData = await hRes.json()
              setProjectHealth(prev => ({ ...prev, [p.id]: hData }))
            }
          } catch {}
        }
      }
      if (incRes.status === 'fulfilled' && incRes.value.ok) setIncidents(await incRes.value.json())
      if (evRes.status === 'fulfilled' && evRes.value.ok) {
        const data = await evRes.value.json()
        setEvents(data.events || [])
      }
      if (provRes.status === 'fulfilled' && provRes.value.ok) setProviders(await provRes.value.json())
      if (rbRes.status === 'fulfilled' && rbRes.value.ok) setRunbooks(await rbRes.value.json())
    } catch (e) {
      console.error('Failed to load dashboard:', e)
    } finally { setLoading(false) }
  }

  const activeIncidents = Array.isArray(incidents) ? incidents.filter(i => i.status !== 'RESOLVED') : []
  const criticalCount = activeIncidents.filter(i => i.severity === 'critical').length
  const configuredProviders = providers.filter(p => p.status !== 'unknown').length
  const healthyProviders = providers.filter(p => p.status === 'healthy').length
  const totalTargets = Object.values(projectHealth).reduce((s, h) => s + (h.total_targets || 0), 0)
  const unhealthyTargets = Object.values(projectHealth).filter(h => h.health === 'unhealthy' || h.health === 'degraded').length

  // ── Empty state ──────────────────────────────────────────────
  if (!loading && projects.length === 0) {
    return (
      <div>
        <div className="page-header">
          <h1>hi.myrepo // COMMAND CENTER</h1>
          <span className="mono" style={{ color: 'var(--text-muted)' }}>
            {new Date().toLocaleTimeString()}
          </span>
        </div>
        <div className="card" style={{
          marginBottom: 'var(--space-lg)',
          background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0, rgba(139, 92, 246, 0.08) 100%)',
          border: '1px solid rgba(59, 130, 246, 0.2)',
        }}>
          <div style={{ textAlign: 'center', padding: 'var(--space-lg)' }}>
            <div style={{ marginBottom: 'var(--space-md)', color: 'var(--accent-blue)' }}><Activity size={32} /></div>
            <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: 'var(--space-sm)' }}>Welcome to hi.myrepo</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', maxWidth: '500px', margin: '0 auto var(--space-lg)' }}>
              Your control plane is ready. Connect your first system to begin observing,
              understanding, and responding to incidents with AI-augmented intelligence.
            </p>
            <button className="btn btn-primary" onClick={() => navigate('/projects')} style={{ fontSize: '14px' }}>
              + Create Your First Project
            </button>
          </div>
        </div>
        <div className="bento-grid" style={{ marginBottom: 'var(--space-md)' }}>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">Projects</div>
            <div className="metric-value">0</div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">AI Providers</div>
            <div className="metric-value" style={{ color: 'var(--text-muted)' }}>Configure</div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="card-title">Runbooks</div>
            <div className="metric-value">{runbooks.length}</div>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><span className="card-title">HOW IT WORKS</span></div>
          <div className="bento-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', padding: 'var(--space-sm)' }}>
            {[
              { icon: <Eye size={24} />, title: 'Observe', desc: 'Ingest events, heartbeats, and telemetry' },
              { icon: <Brain size={24} />, title: 'Understand', desc: 'AI analyzes patterns and identifies root causes' },
              { icon: <Play size={24} />, title: 'Act', desc: 'Propose and approve runbook executions' },
              { icon: <RefreshCw size={24} />, title: 'Autonomy', desc: 'Progressively grant authority as trust builds' },
            ].map((step, i) => (
              <div key={i} style={{ textAlign: 'center' }}>
                <div style={{ marginBottom: 'var(--space-sm)', color: 'var(--accent-blue)' }}>{step.icon}</div>
                <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>{step.title}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{step.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // ── Normal dashboard ─────────────────────────────────────────
  return (
    <div>
      <div className="page-header">
        <h1>hi.myrepo // COMMAND CENTER</h1>
        <span className="mono" style={{ color: 'var(--text-muted)' }}>
          {new Date().toLocaleTimeString()}
        </span>
      </div>

      {/* ── Summary Metrics ─────────────────────────────────────── */}
      <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="card-title">Projects</div>
          <div className="metric-value">{projects.length}</div>
        </div>
        <div className="card">
          <div className="card-title">Monitored Targets</div>
          <div className="metric-value" style={{ color: unhealthyTargets > 0 ? 'var(--accent-orange)' : 'var(--accent-green)' }}>
            {totalTargets}
            {unhealthyTargets > 0 && <span style={{ fontSize: '12px', fontWeight: 400 }}> ({unhealthyTargets} degraded)</span>}
          </div>
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
          <div className="card-title">AI Providers</div>
          <div className="metric-value" style={{ color: healthyProviders > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
            {healthyProviders}<span style={{ fontSize: '12px', fontWeight: 400 }}>/{providers.length} healthy</span>
          </div>
        </div>
        <div className="card">
          <div className="card-title">Recent Events</div>
          <div className="metric-value">{events.length}</div>
        </div>
      </div>

      {/* ── Projects + Event Spine ──────────────────────────────── */}
      <div className="grid-2col" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-md)' }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">PROJECTS</span>
            <button className="btn" onClick={() => navigate('/projects')} style={{ fontSize: '11px', padding: '2px 8px', color: 'var(--accent-blue)' }}>
              View All →
            </button>
          </div>
          {projects.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', padding: 'var(--space-md)', textAlign: 'center' }}>
              {loading ? 'Loading...' : 'No projects yet'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {projects.slice(0, 6).map(p => {
                const h = projectHealth[p.id]
                const health = h?.health || 'unknown'
                return (
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
                      <div className="mono" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
                        {p.slug}
                        {h && <span style={{ marginLeft: '8px' }}>
                          {h.total_targets} target{h.total_targets !== 1 ? 's' : ''}
                        </span>}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="status-badge" style={{ color: healthColors[health] || 'var(--text-muted)', fontSize: '11px' }}>
                        <span className="status-dot" style={{ background: healthColors[health] || 'var(--text-muted)' }}></span>
                        {healthLabels[health] || health}
                      </span>
                      <span className="mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                        {p.monitoring_status === 'active' ? 'MON' : 'OFF'}
                      </span>
                    </div>
                  </div>
                )
              })}
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
              events.slice(0, 15).map(e => (
                <div key={e.id} className="event-item">
                  <span className={`severity-badge ${e.severity || 'low'}`} style={{ minWidth: '50px', textAlign: 'center', fontSize: '10px' }}>
                    {e.severity || '—'}
                  </span>
                  <span className="event-type" style={{ fontSize: '12px' }}>{e.event_type}</span>
                  <span className="event-source" style={{ fontSize: '11px' }}>{e.source}</span>
                  <span className="event-time">
                    {e.received_at ? formatDistanceToNow(new Date(e.received_at), { addSuffix: true }) : ''}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* ── Active Incidents ────────────────────────────────────── */}
      {activeIncidents.length > 0 && (
        <div className="card" style={{ marginTop: 'var(--space-md)' }}>
          <div className="card-header">
            <span className="card-title">ACTIVE INCIDENTS</span>
            <button className="btn" onClick={() => navigate('/incidents')} style={{ fontSize: '11px', padding: '2px 8px', color: 'var(--accent-blue)' }}>
              View All →
            </button>
          </div>
          <table className="responsive-table">
            <thead>
              <tr><th>Severity</th><th>Status</th><th>Title</th><th>Service</th><th>Confidence</th><th>Detected</th></tr>
            </thead>
            <tbody>
              {activeIncidents.map(inc => (
                <tr key={inc.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/incidents/${inc.id}`)}>
                  <td data-label="Severity"><span className={`severity-badge ${inc.severity}`}>{inc.severity}</span></td>
                  <td data-label="Status" className="mono" style={{ fontSize: '12px' }}>{inc.status}</td>
                  <td data-label="Title">{inc.title || inc.fingerprint || 'Unknown'}</td>
                  <td data-label="Service" className="mono" style={{ fontSize: '12px' }}>{inc.affected_service || '—'}</td>
                  <td data-label="Confidence" className="mono">{inc.confidence != null ? `${(inc.confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td data-label="Detected" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {inc.detected_at ? formatDistanceToNow(new Date(inc.detected_at), { addSuffix: true }) : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── System Status ───────────────────────────────────────── */}
      <div className="card" style={{ marginTop: 'var(--space-md)' }}>
        <div className="card-header"><span className="card-title">SYSTEM STATUS</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-sm)', padding: 'var(--space-sm)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={14} style={{ color: 'var(--accent-green)' }} />
            <span style={{ fontSize: '13px' }}>Event Spine</span>
            <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>OPERATIONAL</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={14} style={{ color: 'var(--accent-green)' }} />
            <span style={{ fontSize: '13px' }}>Incident Engine</span>
            <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>OPERATIONAL</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {healthyProviders > 0 ? <CheckCircle size={14} style={{ color: 'var(--accent-green)' }} /> : <AlertTriangle size={14} style={{ color: 'var(--accent-orange)' }} />}
            <span style={{ fontSize: '13px' }}>AI Gateway</span>
            <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
              {healthyProviders > 0 ? 'OPERATIONAL' : configuredProviders > 0 ? 'DEGRADED' : 'NOT CONFIGURED'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Shield size={14} style={{ color: 'var(--accent-blue)' }} />
            <span style={{ fontSize: '13px' }}>Autonomy Level</span>
            <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>OBSERVE ONLY</span>
          </div>
        </div>
      </div>
    </div>
  )
}
