import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Incidents() {
  const [incidents, setIncidents] = useState([])
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadIncidents() }, [filter])

  async function loadIncidents() {
    setLoading(true)
    try {
      const url = filter ? `${API}/incidents?status=${filter}` : `${API}/incidents`
      const [incRes, statsRes] = await Promise.allSettled([
        fetch(url, { headers: authHeaders() }),
        fetch(`${API}/incidents/stats`, { headers: authHeaders() }),
      ])
      if (incRes.status === 'fulfilled' && incRes.value.ok) setIncidents(await incRes.value.json())
      if (statsRes.status === 'fulfilled' && statsRes.value.ok) setStats(await statsRes.value.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const statuses = ['DETECTED', 'TRIAGING', 'INVESTIGATING', 'DIAGNOSED', 'AWAITING_ACTION', 'REMEDIATING', 'VERIFYING', 'RESOLVED', 'REMEDIATION_FAILED', 'ESCALATED']

  return (
    <div>
      <div className="page-header">
        <h1>🔥 Incidents</h1>
        <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
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
        <table>
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
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No incidents - system healthy</td></tr>
            ) : (
              incidents.map(inc => (
                <tr key={inc.id} style={{ cursor: 'pointer' }} onClick={() => window.location.href = `/incidents/${inc.id}`}>
                  <td><span className={`severity-badge ${inc.severity}`}>{inc.severity}</span></td>
                  <td className="mono" style={{ fontSize: '12px' }}>{inc.status}</td>
                  <td>{inc.title || inc.fingerprint || '—'}</td>
                  <td className="mono" style={{ fontSize: '12px' }}>{inc.affected_service || '—'}</td>
                  <td className="mono">{inc.confidence != null ? `${(inc.confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {inc.detected_at ? formatDistanceToNow(new Date(inc.detected_at), { addSuffix: true }) : ''}
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {inc.resolved_at ? formatDistanceToNow(new Date(inc.resolved_at), { addSuffix: true }) : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
