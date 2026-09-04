import { useState, useEffect, useCallback } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { FileText, ChevronLeft, ChevronRight, Filter } from 'lucide-react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')
const PAGE_SIZE = 50

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Audit() {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filters
  const [actionFilter, setActionFilter] = useState('')
  const [actorFilter, setActorFilter] = useState('')
  const [resourceFilter, setResourceFilter] = useState('')
  const [outcomeFilter, setOutcomeFilter] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  const loadLogs = useCallback(async (newOffset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(newOffset))
      if (actionFilter) params.set('action', actionFilter)
      if (actorFilter) params.set('actor_type', actorFilter)
      if (resourceFilter) params.set('resource_type', resourceFilter)
      if (outcomeFilter) params.set('outcome', outcomeFilter)

      const res = await fetch(`${API}/audit?${params}`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setLogs(data.logs || [])
        setTotal(data.total || 0)
        setHasMore(data.has_more || false)
        setOffset(newOffset)
      } else {
        setError(`Failed to load audit logs: ${res.status}`)
      }
    } catch (e) {
      console.error(e)
      setError('Failed to load audit logs')
    } finally {
      setLoading(false)
    }
  }, [actionFilter, actorFilter, resourceFilter, outcomeFilter])

  useEffect(() => { loadLogs(0) }, [loadLogs])

  const pageCount = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  const uniqueActions = [...new Set(logs.map(l => l.action))].sort()

  return (
    <div>
      <div className="page-header">
        <h1><FileText size={20} style={{ verticalAlign: 'middle', marginRight: '8px' }} />Audit Logs</h1>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
          <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            {total > 0 ? `Showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total.toLocaleString()}` : 'No entries'}
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

      {/* Filter bar */}
      {showFilters && (
        <div className="card" style={{ marginBottom: 'var(--space-md)', padding: 'var(--space-sm)' }}>
          <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="text"
              placeholder="Action..."
              value={actionFilter}
              onChange={e => setActionFilter(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') loadLogs(0) }}
              style={selectStyle}
            />
            <select value={actorFilter} onChange={e => { setActorFilter(e.target.value); loadLogs(0) }} style={selectStyle}>
              <option value="">All Actors</option>
              {['user', 'system', 'policy_engine', 'ai'].map(a => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={resourceFilter} onChange={e => { setResourceFilter(e.target.value); loadLogs(0) }} style={selectStyle}>
              <option value="">All Resources</option>
              {['event', 'incident', 'provider', 'project', 'runbook', 'monitoring', 'memory'].map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <select value={outcomeFilter} onChange={e => { setOutcomeFilter(e.target.value); loadLogs(0) }} style={selectStyle}>
              <option value="">All Outcomes</option>
              {['success', 'failure', 'denied'].map(o => <option key={o} value={o}>{o}</option>)}
            </select>
            <button className="btn" onClick={() => loadLogs(0)} style={{ fontSize: '12px', padding: '4px 12px' }}>
              Apply
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="card" style={{ padding: 'var(--space-md)', borderColor: 'var(--accent-red)', marginBottom: 'var(--space-md)' }}>
          <div style={{ color: 'var(--accent-red)', fontSize: '13px' }}>{error}</div>
          <button className="btn" onClick={() => loadLogs(offset)} style={{ marginTop: '8px', fontSize: '12px' }}>Retry</button>
        </div>
      )}

      {/* Table */}
      <div className="card">
        <table className="responsive-table">
          <thead>
            <tr>
              <th>Action</th>
              <th>Actor</th>
              <th>Resource</th>
              <th>Outcome</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</td></tr>
            ) : logs.length === 0 ? (
              <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                {total === 0 ? 'No audit logs match the current filters' : 'No entries found'}
              </td></tr>
            ) : (
              logs.map(l => (
                <tr key={l.id}>
                  <td data-label="Action" className="mono" style={{ fontSize: '12px', color: 'var(--accent-cyan)' }}>{l.action}</td>
                  <td data-label="Actor">
                    <span style={{ fontSize: '12px' }}>
                      <span className="mono" style={{ color: 'var(--text-muted)' }}>{l.actor_type}</span>
                      {l.actor_id && ` / ${l.actor_id.slice(0, 8)}`}
                    </span>
                  </td>
                  <td data-label="Resource" className="mono" style={{ fontSize: '12px' }}>{l.resource_type}</td>
                  <td data-label="Outcome">
                    <span className={`status-badge ${l.outcome === 'success' ? 'healthy' : l.outcome === 'failure' ? 'unhealthy' : 'degraded'}`}>
                      {l.outcome || '—'}
                    </span>
                  </td>
                  <td data-label="Time" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {l.created_at ? formatDistanceToNow(new Date(l.created_at), { addSuffix: true }) : ''}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--space-sm)', marginTop: 'var(--space-md)' }}>
          <button
            className="btn"
            disabled={offset === 0}
            onClick={() => loadLogs(Math.max(0, offset - PAGE_SIZE))}
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
            onClick={() => loadLogs(offset + PAGE_SIZE)}
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
