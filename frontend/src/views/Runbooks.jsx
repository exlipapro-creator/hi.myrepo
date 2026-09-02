import { useState, useEffect } from 'react'
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
        <h1>📋 Runbooks</h1>
      </div>

      <div className="card">
        <table>
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
                  <td className="mono" style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{r.code}</td>
                  <td>{r.name}</td>
                  <td>
                    <span className={`status-badge ${r.status === 'ACTIVE' ? 'healthy' : 'degraded'}`}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ color: r.is_reversible ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    {r.is_reversible ? 'Yes' : 'No'}
                  </td>
                  <td><span className={`severity-badge ${r.max_blast_radius}`}>{r.max_blast_radius}</span></td>
                  <td className="mono">Level {r.required_autonomy_level}</td>
                  <td className="mono" style={{ color: 'var(--accent-green)' }}>{r.historical_success_count}</td>
                  <td className="mono" style={{ color: r.historical_failure_count > 0 ? 'var(--accent-red)' : 'var(--text-secondary)' }}>
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
