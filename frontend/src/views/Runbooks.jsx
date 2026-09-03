import { useState, useEffect } from 'react'
import { BookOpen } from 'lucide-react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Runbooks() {
  const [runbooks, setRunbooks] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadRunbooks() }, [])

  async function loadRunbooks() {
    try {
      const res = await fetch(`${API}/runbooks`, { headers: authHeaders() })
      if (res.ok) setRunbooks(await res.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <h1><BookOpen size={20} style={{ verticalAlign: 'middle', marginRight: '8px' }} />Runbooks</h1>
      </div>

      <div className="card">
        <table className="responsive-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Status</th>
              <th>Reversible</th>
              <th>Blast Radius</th>
              <th>Min Autonomy</th>
              <th>Successes</th>
              <th>Failures</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</td></tr>
            ) : runbooks.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                No runbooks defined. Seed from database/seeds/default_runbooks.json.
              </td></tr>
            ) : (
              runbooks.map(r => (
                <tr key={r.id}>
                  <td data-label="Code" className="mono" style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{r.code}</td>
                  <td data-label="Name">{r.name}</td>
                  <td data-label="Status">
                    <span className={`status-badge ${r.status === 'ACTIVE' ? 'healthy' : 'degraded'}`}>
                      {r.status}
                    </span>
                  </td>
                  <td data-label="Reversible" style={{ color: r.is_reversible ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    {r.is_reversible ? 'Yes' : 'No'}
                  </td>
                  <td data-label="Blast Radius"><span className={`severity-badge ${r.max_blast_radius}`}>{r.max_blast_radius}</span></td>
                  <td data-label="Min Autonomy" className="mono">Level {r.required_autonomy_level}</td>
                  <td data-label="Successes" className="mono" style={{ color: 'var(--accent-green)' }}>{r.historical_success_count}</td>
                  <td data-label="Failures" className="mono" style={{ color: r.historical_failure_count > 0 ? 'var(--accent-red)' : 'var(--text-secondary)' }}>
                    {r.historical_failure_count}
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
