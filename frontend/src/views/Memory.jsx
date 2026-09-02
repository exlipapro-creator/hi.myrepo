import { useState } from 'react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function Memory() {
  const [fingerprint, setFingerprint] = useState('')
  const [category, setCategory] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  async function search() {
    if (!fingerprint && !category) return
    setLoading(true)
    setSearched(true)
    try {
      const params = new URLSearchParams()
      if (fingerprint) params.set('fingerprint', fingerprint)
      if (category) params.set('category', category)
      params.set('limit', '20')

      const res = await fetch(`${API}/memory/search?${params}`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setResults(data.records || [])
      }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <h1>🧠 Memory</h1>
      </div>

      {/* Search */}
      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <div className="metric-label" style={{ marginBottom: '4px' }}>Fingerprint</div>
            <input
              type="text"
              value={fingerprint}
              onChange={e => setFingerprint(e.target.value)}
              placeholder="Search by error fingerprint..."
              style={{
                width: '100%', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)', padding: '6px 10px', color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)', fontSize: '13px',
              }}
            />
          </div>
          <div>
            <div className="metric-label" style={{ marginBottom: '4px' }}>Category</div>
            <select
              value={category}
              onChange={e => setCategory(e.target.value)}
              style={{
                background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)', padding: '6px 10px', color: 'var(--text-primary)', fontSize: '13px',
              }}
            >
              <option value="">All</option>
              <option value="incident">Incident</option>
              <option value="resolution">Resolution</option>
              <option value="postmortem">Postmortem</option>
              <option value="pattern">Pattern</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={search} disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

      {/* Results */}
      {searched && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">{results.length} result(s) found</span>
          </div>
          {results.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 'var(--space-lg)' }}>
              No memory records found for this search.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
              {results.map(r => (
                <div key={r.id} style={{
                  padding: 'var(--space-md)', background: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h3 style={{ fontSize: '14px', fontWeight: 600 }}>{r.title}</h3>
                      <span className="mono" style={{
                        fontSize: '11px', color: 'var(--accent-cyan)',
                        padding: '1px 6px', borderRadius: '4px', background: 'rgba(6, 182, 212, 0.1)',
                      }}>
                        {r.category}
                      </span>
                    </div>
                    <span className={`status-badge ${r.success ? 'healthy' : 'unhealthy'}`}>
                      {r.success ? 'SUCCESS' : 'FAILED'}
                    </span>
                  </div>
                  <p style={{ marginTop: 'var(--space-sm)', color: 'var(--text-secondary)', fontSize: '13px' }}>
                    {r.summary}
                  </p>
                  {r.root_cause && (
                    <div style={{ marginTop: 'var(--space-sm)' }}>
                      <span className="metric-label">Root Cause: </span>
                      <span className="mono" style={{ fontSize: '12px' }}>{r.root_cause}</span>
                    </div>
                  )}
                  {r.resolution && (
                    <div style={{ marginTop: 'var(--space-xs)' }}>
                      <span className="metric-label">Resolution: </span>
                      <span style={{ fontSize: '12px' }}>{r.resolution}</span>
                    </div>
                  )}
                  {r.runbook_code && (
                    <div style={{ marginTop: 'var(--space-xs)' }}>
                      <span className="metric-label">Runbook: </span>
                      <span className="mono" style={{ fontSize: '12px', color: 'var(--accent-cyan)' }}>{r.runbook_code}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
