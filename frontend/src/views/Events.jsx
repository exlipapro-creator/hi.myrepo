import { useState, useEffect, useCallback } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Radio, ChevronLeft, ChevronRight, Filter } from 'lucide-react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')
const PAGE_SIZE = 50

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Events() {
  const [events, setEvents] = useState([])
  const [stats, setStats] = useState(null)
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filters
  const [typeFilter, setTypeFilter] = useState('')
  const [sevFilter, setSevFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [incidentFilter, setIncidentFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  const loadEvents = useCallback(async (newOffset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(newOffset))
      if (typeFilter) params.set('event_type', typeFilter)
      if (sevFilter) params.set('severity', sevFilter)
      if (sourceFilter) params.set('source', sourceFilter)
      if (incidentFilter) params.set('incident_id', incidentFilter)
      if (fromDate) params.set('from_date', fromDate)
      if (toDate) params.set('to_date', toDate)

      const [evRes, statsRes] = await Promise.allSettled([
        fetch(`${API}/events?${params}`, { headers: authHeaders() }),
        ...(newOffset === 0 ? [fetch(`${API}/events/stats`, { headers: authHeaders() })] : []),
      ])
      if (evRes.status === 'fulfilled' && evRes.value.ok) {
        const data = await evRes.value.json()
        setEvents(data.events || [])
        setTotal(data.total || 0)
        setHasMore(data.has_more || false)
        setOffset(newOffset)
      } else if (evRes.status === 'fulfilled') {
        setError(`Failed to load events: ${evRes.value.status}`)
      } else {
        setError('Network error loading events')
      }
      if (statsRes?.status === 'fulfilled' && statsRes.value?.ok) {
        setStats(await statsRes.value.json())
      }
    } catch (e) {
      console.error(e)
      setError('Failed to load events')
    } finally {
      setLoading(false)
    }
  }, [typeFilter, sevFilter, sourceFilter, incidentFilter, fromDate, toDate])

  useEffect(() => { loadEvents(0) }, [loadEvents])

  const pageCount = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div>
      <div className="page-header">
        <h1><Radio size={20} style={{ verticalAlign: 'middle', marginRight: '8px' }} />Event Explorer</h1>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
          <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            {total > 0 ? `Showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total.toLocaleString()}` : 'No events'}
          </span>
          <button
            className="btn"
            onClick={() => setShowFilters(!showFilters)}
            style={{ fontSize: '12px', padding: '4px 8px' }}
          >
            <Filter size={14} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
            Filters
          </button>
        </div>
      </div>

      {/* Collapsible filter bar */}
      {showFilters && (
        <div className="card" style={{ marginBottom: 'var(--space-md)', padding: 'var(--space-sm)' }}>
          <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap', alignItems: 'center' }}>
            <select value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setOffset(0) }} style={selectStyle}>
              <option value="">All Types</option>
              {['HEARTBEAT_SUCCESS', 'HEARTBEAT_FAILURE', 'HEARTBEAT_DEGRADED', 'ERROR_DETECTED',
                'DEPLOYMENT_SUCCEEDED', 'DEPLOYMENT_FAILED', 'AI_REQUEST_SUCCEEDED', 'AI_PROVIDER_FAILED',
                'INCIDENT_CREATED', 'INCIDENT_RESOLVED', 'RUNBOOK_PROPOSED', 'VERIFICATION_SUCCEEDED'
              ].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={sevFilter} onChange={e => { setSevFilter(e.target.value); setOffset(0) }} style={selectStyle}>
              <option value="">All Severities</option>
              {['low', 'medium', 'high', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <input
              type="text"
              placeholder="Source..."
              value={sourceFilter}
              onChange={e => setSourceFilter(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { setOffset(0); loadEvents(0) } }}
              style={{ ...selectStyle, width: '120px' }}
            />
            <input
              type="text"
              placeholder="Incident ID..."
              value={incidentFilter}
              onChange={e => setIncidentFilter(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { setOffset(0); loadEvents(0) } }}
              style={{ ...selectStyle, width: '200px' }}
            />
            <input
              type="datetime-local"
              value={fromDate}
              onChange={e => { setFromDate(e.target.value); setOffset(0) }}
              style={selectStyle}
              title="From date"
            />
            <input
              type="datetime-local"
              value={toDate}
              onChange={e => { setToDate(e.target.value); setOffset(0) }}
              style={selectStyle}
              title="To date"
            />
            <button className="btn" onClick={() => loadEvents(0)} style={{ fontSize: '12px', padding: '4px 12px' }}>
              Apply
            </button>
          </div>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card">
            <div className="card-title">Total Events</div>
            <div className="metric-value">{stats.total_events?.toLocaleString() || 0}</div>
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

      {/* Error state */}
      {error && (
        <div className="card" style={{ padding: 'var(--space-md)', borderColor: 'var(--accent-red)', marginBottom: 'var(--space-md)' }}>
          <div style={{ color: 'var(--accent-red)', fontSize: '13px' }}>{error}</div>
          <button className="btn" onClick={() => loadEvents(offset)} style={{ marginTop: '8px', fontSize: '12px' }}>Retry</button>
        </div>
      )}

      {/* Event list */}
      <div className="card" style={{ overflowX: 'auto' }}>
        <div className="event-stream">
          {loading ? (
            <div style={{ padding: 'var(--space-md)', textAlign: 'center', color: 'var(--text-muted)' }}>Loading events...</div>
          ) : events.length === 0 ? (
            <div style={{ padding: 'var(--space-lg)', textAlign: 'center', color: 'var(--text-muted)' }}>
              {total === 0 ? 'No events match the current filters' : 'No events found'}
            </div>
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
                    corr: {e.correlation_id.slice(0, 8)}
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

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--space-sm)', marginTop: 'var(--space-md)' }}>
          <button
            className="btn"
            disabled={offset === 0}
            onClick={() => loadEvents(Math.max(0, offset - PAGE_SIZE))}
            style={{ fontSize: '12px', padding: '4px 12px', opacity: offset === 0 ? 0.4 : 1 }}
          >
            <ChevronLeft size={14} /> Prev
          </button>
          <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            Page {currentPage} of {pageCount}
          </span>
          <button
            className="btn"
            disabled={!hasMore}
            onClick={() => loadEvents(offset + PAGE_SIZE)}
            style={{ fontSize: '12px', padding: '4px 12px', opacity: hasMore ? 1 : 0.4 }}
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  )
}

const selectStyle = {
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border-primary)',
  borderRadius: 'var(--radius-sm)',
  padding: '4px 8px',
  color: 'var(--text-primary)',
  fontSize: '13px',
}
