import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadProjects() }, [])

  async function loadProjects() {
    try {
      const res = await fetch(`${API}/projects`, { headers: authHeaders() })
      if (res.ok) setProjects(await res.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <h1>📦 Projects</h1>
      </div>

      <div className="bento-grid">
        {loading ? (
          <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
        ) : projects.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', gridColumn: '1 / -1' }}>
            No projects yet. Create one via the API to start monitoring.
          </div>
        ) : (
          projects.map(p => (
            <div key={p.id} className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>{p.name}</h3>
                  <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{p.slug}</span>
                </div>
                <span className="status-badge healthy">
                  <span className="status-dot healthy"></span>
                  {p.is_active ? 'ACTIVE' : 'INACTIVE'}
                </span>
              </div>
              {p.description && (
                <p style={{ marginTop: 'var(--space-sm)', color: 'var(--text-secondary)', fontSize: '13px' }}>
                  {p.description}
                </p>
              )}
              <div style={{ marginTop: 'var(--space-md)', display: 'flex', gap: 'var(--space-md)' }}>
                <div>
                  <div className="metric-label">Autonomy</div>
                  <div className="mono" style={{ fontSize: '13px' }}>Level {p.autonomy_level}</div>
                </div>
                {p.repository_url && (
                  <div>
                    <div className="metric-label">Repository</div>
                    <a href={p.repository_url} target="_blank" rel="noopener" style={{
                      color: 'var(--accent-blue)', fontSize: '13px', textDecoration: 'none',
                    }}>
                      {p.repository_url.replace('https://github.com/', '')}
                    </a>
                  </div>
                )}
                <div>
                  <div className="metric-label">Created</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                    {p.created_at ? formatDistanceToNow(new Date(p.created_at), { addSuffix: true }) : '—'}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
