import { useState, useEffect } from 'react'
import { Activity, AlertTriangle, CheckCircle, Clock, Zap } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

export default function Dashboard() {
  const [projects, setProjects] = useState([])
  const [incidents, setIncidents] = useState([])
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [projRes, incRes, evRes] = await Promise.allSettled([
        fetch(`${API}/projects`, { headers: authHeaders() }),
        fetch(`${API}/incidents?limit=10`, { headers: authHeaders() }),
        fetch(`${API}/events?limit=20`, { headers: authHeaders() }),
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
          </div>
          {projects.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', padding: 'var(--space-md)', textAlign: 'center' }}>
              {loading ? 'Loading...' : 'No projects yet. Create one to get started.'}
            </div>
          ) : (
            <div className="bento-grid" style={{ gridTemplateColumns: '1fr' }}>
              {projects.map(p => (
                <div key={p.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: 'var(--space-sm)', borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-secondary)',
                }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>{p.name}</div>
                    <div className="mono" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{p.slug}</div>
                  </div>
                  <span className="status-badge healthy">
                    <span className="status-dot healthy"></span>
                    HEALTHY
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
                <tr key={inc.id}>
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
