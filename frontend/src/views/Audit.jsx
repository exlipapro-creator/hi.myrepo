import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { FileText } from 'lucide-react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Audit() {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadLogs() }, [])

  async function loadLogs() {
    try {
      const res = await fetch(`${API}/audit?limit=100`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setLogs(data.logs || [])
        setTotal(data.total || 0)
      }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <h1><FileText size={20} style={{ verticalAlign: 'middle', marginRight: '8px' }} />Audit Logs</h1>
        <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
          {total} total entries
        </span>
      </div>

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
              <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No audit logs yet</td></tr>
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
    </div>
  )
}
