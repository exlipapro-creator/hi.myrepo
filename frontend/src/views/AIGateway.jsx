import { useState, useEffect } from 'react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function ProviderCard({ provider }) {
  const stateColors = {
    closed: 'var(--accent-green)',
    open: 'var(--accent-red)',
    half_open: 'var(--accent-yellow)',
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-md)' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 600, textTransform: 'capitalize' }}>
          {provider.name}
        </h3>
        <span className={`status-badge ${provider.status}`}>
          <span className={`status-dot ${provider.status}`}></span>
          {provider.status}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-sm)' }}>
        <div>
          <div className="metric-label">Success Rate</div>
          <div className="mono" style={{
            fontSize: '14px',
            color: provider.success_rate >= 0.95 ? 'var(--accent-green)' :
              provider.success_rate >= 0.8 ? 'var(--accent-yellow)' : 'var(--accent-red)',
          }}>
            {(provider.success_rate * 100).toFixed(1)}%
          </div>
        </div>
        <div>
          <div className="metric-label">Avg Latency</div>
          <div className="mono" style={{ fontSize: '14px' }}>
            {provider.avg_latency_ms.toFixed(0)}ms
          </div>
        </div>
        <div>
          <div className="metric-label">Total Requests</div>
          <div className="mono" style={{ fontSize: '14px' }}>{provider.total_requests}</div>
        </div>
        <div>
          <div className="metric-label">Failures</div>
          <div className="mono" style={{
            fontSize: '14px',
            color: provider.total_failures > 0 ? 'var(--accent-red)' : 'var(--text-secondary)',
          }}>
            {provider.total_failures}
          </div>
        </div>
        <div>
          <div className="metric-label">Circuit State</div>
          <div className="mono" style={{
            fontSize: '14px',
            color: stateColors[provider.circuit_state] || 'var(--text-secondary)',
          }}>
            {provider.circuit_state}
          </div>
        </div>
        <div>
          <div className="metric-label">Rate Limits (429)</div>
          <div className="mono" style={{
            fontSize: '14px',
            color: provider.recent_429_count > 0 ? 'var(--accent-orange)' : 'var(--text-secondary)',
          }}>
            {provider.recent_429_count}
          </div>
        </div>
      </div>

      {provider.cooldown_until && (
        <div style={{
          marginTop: 'var(--space-sm)', padding: 'var(--space-xs) var(--space-sm)',
          background: 'rgba(245, 158, 11, 0.1)', borderRadius: 'var(--radius-sm)',
          border: '1px solid rgba(245, 158, 11, 0.2)', fontSize: '12px', color: 'var(--accent-yellow)',
        }}>
          ⏳ Cooldown until: {new Date(provider.cooldown_until).toLocaleString()}
        </div>
      )}

      {provider.capabilities && provider.capabilities.length > 0 && (
        <div style={{ marginTop: 'var(--space-md)' }}>
          <div className="metric-label" style={{ marginBottom: '4px' }}>Capabilities</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {provider.capabilities.map(cap => (
              <span key={cap} style={{
                padding: '2px 6px', borderRadius: '4px', fontSize: '10px',
                background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
                fontFamily: 'var(--font-mono)',
              }}>
                {cap}
              </span>
            ))}
          </div>
        </div>
      )}

      {provider.models_available && provider.models_available.length > 0 && (
        <div style={{ marginTop: 'var(--space-sm)' }}>
          <div className="metric-label" style={{ marginBottom: '4px' }}>Models</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {provider.models_available.map(model => (
              <span key={model} style={{
                padding: '2px 6px', borderRadius: '4px', fontSize: '10px',
                background: 'rgba(59, 130, 246, 0.1)', color: 'var(--accent-blue)',
                fontFamily: 'var(--font-mono)',
              }}>
                {model}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function AIGateway() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadProviders() }, [])

  async function loadProviders() {
    try {
      const res = await fetch(API + '/providers', { headers: authHeaders() })
      if (res.ok) setProviders(await res.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const healthyCount = providers.filter(p => p.status === 'healthy').length
  const circuitOpen = providers.filter(p => p.circuit_state === 'open').length
  const totalRequests = providers.reduce((sum, p) => sum + p.total_requests, 0)

  return (
    <div>
      <div className="page-header">
        <h1>🤖 AI Gateway</h1>
        <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
          /v1/chat/completions
        </span>
      </div>

      {/* Summary */}
      <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="card-title">Providers</div>
          <div className="metric-value">{providers.length}</div>
        </div>
        <div className="card">
          <div className="card-title">Healthy</div>
          <div className="metric-value" style={{ color: healthyCount > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
            {healthyCount}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Circuit Open</div>
          <div className="metric-value" style={{ color: circuitOpen > 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
            {circuitOpen}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Total Requests</div>
          <div className="metric-value">{totalRequests}</div>
        </div>
      </div>

      {/* Provider Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: 'var(--space-md)' }}>
        {loading ? (
          <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 'var(--space-lg)' }}>
            Loading providers...
          </div>
        ) : providers.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', padding: 'var(--space-xl)' }}>
            <div style={{ fontSize: '32px', marginBottom: 'var(--space-md)' }}>🤖</div>
            <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: 'var(--space-sm)' }}>
              No providers configured
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
              Add API keys to your environment to enable AI-powered incident analysis.
            </p>
            <div style={{
              marginTop: 'var(--space-md)', padding: 'var(--space-sm)',
              background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-muted)',
              textAlign: 'left',
            }}>
              GEMINI_API_KEY=your-key-here
            </div>
          </div>
        ) : (
          providers.map(p => (
            <ProviderCard key={p.name} provider={p} />
          ))
        )}
      </div>
    </div>
  )
}
