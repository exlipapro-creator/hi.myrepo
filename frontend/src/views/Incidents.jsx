import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')
const PAGE_SIZE = 50

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Incidents() {
  const [incidents, setIncidents] = useState([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadIncidents(0) }, [filter])

  async function loadIncidents(newOffset = 0) {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(newOffset))
      if (filter) params.set('status', filter)

      const [incRes, statsRes] = await Promise.allSettled([
        fetch(`${API}/incidents?${params}`, { headers: authHeaders() }),
        ...(newOffset === 0 ? [fetch(`${API}/incidents/stats`, { headers: authHeaders() })] : []),
      ])
      if (incRes.status === 'fulfilled' && incRes.value.ok) {
        const data = await incRes.value.json()
        setIncidents(data.incidents || [])
        setTotal(data.total || 0)
        setHasMore(data.has_more || false)
        setOffset(newOffset)
      } else if (incRes.status === 'fulfilled') {
        setIncidents([])
      }
      if (statsRes?.status === 'fulfilled' && statsRes.value?.ok) {
        setStats(await statsRes.value.json())
      }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const statuses = ['DETECTED', 'TRIAGING', 'INVESTIGATING', 'DIAGNOSED', 'AWAITING_ACTION', 'REMEDIATING', 'VERIFYING', 'RESOLVED', 'REMEDIATION_FAILED', 'ESCALATED']
  const pageCount = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div>
      <div className="page-header">
        <h1><AlertTriangle size={20} style={{ verticalAlign: 'middle', marginRight: '8px' }} />Incidents</h1>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
          <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            {total > 0 ? `${total} total` : ''}
          </span>
          <select
            value={filter}
            onChange={e => { setFilter(e.target.value); setOffset(0) }}
            style={{
              background: 'var(--bg-elevated)', border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          >
            <option value="">All Statuses</option>
            {statuses.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card">
            <div className="card-title">Total</div>
            <div className="metric-value">{stats.total}</div>
          </div>
          {Object.entries(stats.by_severity || {}).map(([sev, count]) => (
            <div className="card" key={sev}>
              <div className="card-title">{sev}</div>
              <div className="metric-value">
                <span className={`severity-badge ${sev}`} style={{ fontSize: '16px' }}>{count}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="card">
        <table className="responsive-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Status</th>
              <th>Title</th>
              <th>Service</th>
              <th>Confidence</th>
              <th>Detected</th>
              <th>Resolved</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</td></tr>
            ) : incidents.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                {total === 0 ? 'No incidents — system healthy' : 'No incidents match filter'}
              </td></tr>
            ) : (
              incidents.map(inc => (
                <tr key={inc.id} style={{ cursor: 'pointer' }} onClick={() => window.location.href = `/incidents/${inc.id}`}>
                  <td data-label="Severity"><span className={`severity-badge ${inc.severity}`}>{inc.severity}</span></td>
                  <td data-label="Status" className="mono" style={{ fontSize: '12px' }}>{inc.status}</td>
                  <td data-label="Title">{inc.title || inc.fingerprint || '—'}</td>
                  <td data-label="Service" className="mono" style={{ fontSize: '12px' }}>{inc.affected_service || '—'}</td>
                  <td data-label="Confidence" className="mono">{inc.confidence != null ? `${(inc.confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td data-label="Detected" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {inc.detected_at ? formatDistanceToNow(new Date(inc.detected_at), { addSuffix: true }) : ''}
                  </td>
                  <td data-label="Resolved" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {inc.resolved_at ? formatDistanceToNow(new Date(inc.resolved_at), { addSuffix: true }) : '—'}
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
            onClick={() => loadIncidents(Math.max(0, offset - PAGE_SIZE))}
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
            onClick={() => loadIncidents(offset + PAGE_SIZE)}
            style={{ fontSize: '12px', padding: '4px 12px', opacity: hasMore ? 1 : 0.4 }}
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
