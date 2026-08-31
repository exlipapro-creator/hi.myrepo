import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'

const API = '/api/v1'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Events() {
  const [events, setEvents] = useState([])
  const [stats, setStats] = useState(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [sevFilter, setSevFilter] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadEvents() }, [typeFilter, sevFilter])

  async function loadEvents() {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (typeFilter) params.set('event_type', typeFilter)
      if (sevFilter) params.set('severity', sevFilter)
      params.set('limit', '100')

      const [evRes, statsRes] = await Promise.allSettled([
        fetch(`${API}/events?${params}`, { headers: authHeaders() }),
        fetch(`${API}/events/stats`, { headers: authHeaders() }),
      ])
      if (evRes.status === 'fulfilled' && evRes.value.ok) {
        const data = await evRes.value.json()
        setEvents(data.events || [])
      }
      if (statsRes.status === 'fulfilled' && statsRes.value.ok) setStats(await statsRes.value.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <h1>📡 Event Explorer</h1>
        <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{
            background: 'var(--bg-elevated)', border: '1px solid var(--border-primary)',
            borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--text-primary)', fontSize: '13px',
          }}>
            <option value="">All Types</option>
            {['HEARTBEAT_SUCCESS', 'HEARTBEAT_FAILURE', 'ERROR_DETECTED', 'DEPLOYMENT_SUCCEEDED',
              'DEPLOYMENT_FAILED', 'AI_REQUEST_SUCCEEDED', 'AI_PROVIDER_FAILED', 'INCIDENT_CREATED',
              'INCIDENT_RESOLVED', 'RUNBOOK_PROPOSED', 'VERIFICATION_SUCCEEDED'].map(t =>
              <option key={t} value={t}>{t}</option>
            )}
          </select>
          <select value={sevFilter} onChange={e => setSevFilter(e.target.value)} style={{
            background: 'var(--bg-elevated)', border: '1px solid var(--border-primary)',
            borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--text-primary)', fontSize: '13px',
          }}>
            <option value="">All Severities</option>
            {['low', 'medium', 'high', 'critical'].map(s =>
              <option key={s} value={s}>{s}</option>
            )}
          </select>
        </div>
      </div>

      {stats && (
        <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card">
            <div className="card-title">Total Events</div>
            <div className="metric-value">{stats.total_events}</div>
          </div>
          <div className="card">
            <div className="card-title">Event Types</div>
            <div className="metric-value">{Object.keys(stats.by_type || {}).length}</div>
          </div>
          <div className="card">
            <div className="card-title">Errors</div>
            <div className="metric-value" style={{ color: 'var(--accent-red)' }}>
              {(stats.by_type || {}).ERROR_DETECTED || 0}
            </div>
          </div>
          <div className="card">
            <div className="card-title">Heartbeats</div>
            <div className="metric-value" style={{ color: 'var(--accent-green)' }}>
              {(stats.by_type || {}).HEARTBEAT_SUCCESS || 0}
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="event-stream">
          {loading ? (
            <div style={{ padding: 'var(--space-md)', textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
          ) : events.length === 0 ? (
            <div style={{ padding: 'var(--space-md)', textAlign: 'center', color: 'var(--text-muted)' }}>No events found</div>
          ) : (
            events.map(e => (
              <div key={e.id} className="event-item" style={{ padding: 'var(--space-sm)' }}>
                <span className={`severity-badge ${e.severity || 'low'}`} style={{ minWidth: '60px', textAlign: 'center' }}>
                  {e.severity || '—'}
                </span>
                <span className="event-type">{e.event_type}</span>
                <span className="mono" style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>
                  {e.source_type}
                </span>
                <span className="event-source">{e.source}</span>
                {e.correlation_id && (
                  <span className="mono" style={{ color: 'var(--accent-purple)', fontSize: '10px' }}>
                    correlation: {e.correlation_id.slice(0, 8)}
                  </span>
                )}
                <span className="event-time">
                  {e.received_at ? formatDistanceToNow(new Date(e.received_at), { addSuffix: true }) : ''}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
