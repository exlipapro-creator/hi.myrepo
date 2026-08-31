import { useState, useEffect } from 'react'

const API = '/api/v1'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function AIGateway() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadProviders() }, [])

  async function loadProviders() {
    try {
      const res = await fetch('/v1/providers', { headers: authHeaders() })
      if (res.ok) setProviders(await res.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <h1>🤖 AI Gateway</h1>
        <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
          /v1/chat/completions
        </span>
      </div>

      <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="card-title">Providers</div>
          <div className="metric-value">{providers.length}</div>
        </div>
        <div className="card">
          <div className="card-title">Healthy</div>
          <div className="metric-value" style={{ color: 'var(--accent-green)' }}>
            {providers.filter(p => p.status === 'healthy').length}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Circuit Open</div>
          <div className="metric-value" style={{ color: 'var(--accent-red)' }}>
            {providers.filter(p => p.circuit_state === 'open').length}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 'var(--space-md)' }}>
        {loading ? (
          <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
        ) : providers.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
            No providers configured. Add API keys to .env.
          </div>
        ) : (
          providers.map(p => (
            <div key={p.name} className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-md)' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600, textTransform: 'capitalize' }}>{p.name}</h3>
                <span className={`status-badge ${p.status}`}>
                  <span className={`status-dot ${p.status}`}></span>
                  {p.status}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-sm)' }}>
                <div>
                  <div className="metric-label">Success Rate</div>
                  <div className="mono" style={{ fontSize: '14px' }}>
                    {(p.success_rate * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="metric-label">Avg Latency</div>
                  <div className="mono" style={{ fontSize: '14px' }}>
                    {p.avg_latency_ms.toFixed(0)}ms
                  </div>
                </div>
                <div>
                  <div className="metric-label">Total Requests</div>
                  <div className="mono" style={{ fontSize: '14px' }}>{p.total_requests}</div>
                </div>
                <div>
                  <div className="metric-label">Failures</div>
                  <div className="mono" style={{ fontSize: '14px', color: p.total_failures > 0 ? 'var(--accent-red)' : 'var(--text-secondary)' }}>
                    {p.total_failures}
                  </div>
                </div>
                <div>
                  <div className="metric-label">Circuit State</div>
                  <div className="mono" style={{
                    fontSize: '14px',
                    color: p.circuit_state === 'closed' ? 'var(--accent-green)' :
                           p.circuit_state === 'open' ? 'var(--accent-red)' : 'var(--accent-yellow)',
                  }}>
                    {p.circuit_state}
                  </div>
                </div>
                <div>
                  <div className="metric-label">429s</div>
                  <div className="mono" style={{ fontSize: '14px' }}>{p.recent_429_count}</div>
                </div>
              </div>

              {p.capabilities && p.capabilities.length > 0 && (
                <div style={{ marginTop: 'var(--space-md)' }}>
                  <div className="metric-label" style={{ marginBottom: '4px' }}>Capabilities</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {p.capabilities.map(c => (
                      <span key={c} style={{
                        padding: '2px 6px', borderRadius: '4px', fontSize: '10px',
                        background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
                        fontFamily: 'var(--font-mono)',
                      }}>
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
