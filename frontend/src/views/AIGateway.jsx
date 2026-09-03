import { useState, useEffect } from 'react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/v1')
const API_V1 = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function ProviderCard({ provider, isAdmin, onTest, onToggle, onDelete, onReplaceKey, testing }) {
  const stateColors = {
    closed: 'var(--accent-green)',
    open: 'var(--accent-red)',
    half_open: 'var(--accent-yellow)',
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-md)' }}>
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: 600 }}>
            {provider.display_name || provider.name}
          </h3>
          <span className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {provider.name}
          </span>
        </div>
        <span className={`status-badge ${provider.status}`}>
          <span className={`status-dot ${provider.status}`}></span>
          {provider.status}
        </span>
      </div>

      {/* Configuration Status */}
      <div style={{
        padding: 'var(--space-sm)', marginBottom: 'var(--space-md)',
        background: provider.is_configured ? 'rgba(34, 197, 94, 0.08)' : 'rgba(245, 158, 11, 0.08)',
        border: `1px solid ${provider.is_configured ? 'rgba(34, 197, 94, 0.2)' : 'rgba(245, 158, 11, 0.2)'}`,
        borderRadius: 'var(--radius-sm)', fontSize: '12px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: provider.is_configured ? 'var(--accent-green)' : 'var(--accent-yellow)' }}>
            {provider.is_configured ? '🔑 API Key Configured' : '⚠️ Not Configured'}
          </span>
          {provider.is_configured && provider.key_last_four && (
            <span className="mono" style={{ color: 'var(--text-muted)' }}>
              ••••••••{provider.key_last_four}
            </span>
          )}
        </div>
        {provider.configured_at && (
          <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>
            Configured: {new Date(provider.configured_at).toLocaleDateString()}
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-sm)' }}>
        <div>
          <div className="metric-label">Success Rate</div>
          <div className="mono" style={{
            fontSize: '14px',
            color: provider.total_requests === 0 ? 'var(--text-muted)' :
              provider.success_rate >= 0.95 ? 'var(--accent-green)' :
              provider.success_rate >= 0.8 ? 'var(--accent-yellow)' : 'var(--accent-red)',
          }}>
            {provider.total_requests === 0 ? 'No requests' : `${(provider.success_rate * 100).toFixed(1)}%`}
          </div>
        </div>
        <div>
          <div className="metric-label">Avg Latency</div>
          <div className="mono" style={{ fontSize: '14px' }}>
            {provider.total_requests === 0 ? '—' : `${provider.avg_latency_ms.toFixed(0)}ms`}
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

      {/* Admin Actions */}
      {isAdmin && (
        <div style={{ marginTop: 'var(--space-md)', display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
          <button
            className="btn"
            onClick={() => onTest(provider.name)}
            disabled={testing === provider.name || !provider.is_configured}
            style={{ fontSize: '11px', flex: 1 }}
          >
            {testing === provider.name ? 'Testing...' : 'Test Connection'}
          </button>
          <button
            className="btn"
            onClick={() => onToggle(provider.name, provider.status !== 'disabled')}
            style={{
              fontSize: '11px',
              color: provider.status === 'disabled' ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          >
            {provider.status === 'disabled' ? 'Enable' : 'Disable'}
          </button>
          {provider.is_configured && (
            <button
              className="btn"
              onClick={() => onReplaceKey(provider.name)}
              style={{ fontSize: '11px', color: 'var(--accent-yellow)' }}
            >
              Replace Key
            </button>
          )}
          <button
            className="btn"
            onClick={() => onDelete(provider.name)}
            style={{ fontSize: '11px', color: 'var(--accent-red)' }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

function AddProviderForm({ onCreated, onCancel }) {
  const [provider, setProvider] = useState('gemini')
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${API_V1}/providers`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: provider, api_key: apiKey }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Failed to configure provider')
        return
      }
      onCreated(data)
    } catch (err) {
      setError('Connection failed')
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = {
    width: '100%', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
    borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text-primary)',
    fontSize: '13px', outline: 'none', fontFamily: 'inherit',
  }

  return (
    <div className="card" style={{ maxWidth: '500px' }}>
      <div className="card-header">
        <span className="card-title">ADD PROVIDER</span>
      </div>
      {error && (
        <div style={{
          padding: '8px 12px', borderRadius: 'var(--radius-sm)',
          background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
          color: 'var(--accent-red)', fontSize: '13px', marginBottom: 'var(--space-md)',
        }}>
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 'var(--space-md)' }}>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }}>
            Provider
          </label>
          <select value={provider} onChange={e => setProvider(e.target.value)} style={inputStyle}>
            <option value="gemini">Google Gemini</option>
            <option value="openai">OpenAI</option>
            <option value="groq">Groq</option>
          </select>
        </div>
        <div style={{ marginBottom: 'var(--space-md)' }}>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }}>
            API Key
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="Enter your API key"
            required
            minLength={8}
            style={{ ...inputStyle, fontFamily: 'var(--font-mono)' }}
          />
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            🔒 Key is encrypted before storage. Never returned in responses.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <button type="submit" disabled={loading} className="btn btn-primary" style={{ flex: 1 }}>
            {loading ? 'Configuring...' : 'Configure Provider'}
          </button>
          <button type="button" onClick={onCancel} className="btn" style={{ color: 'var(--text-muted)' }}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

export default function AIGateway() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [testing, setTesting] = useState(null)
  const [testResult, setTestResult] = useState(null)
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    loadProviders()
    checkAdmin()
  }, [])

  async function checkAdmin() {
    try {
      const res = await fetch(`${API_V1}/auth/me`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setIsAdmin(data.role === 'admin')
      }
    } catch {}
  }

  async function loadProviders() {
    try {
      const res = await fetch(`${API_V1}/providers`, { headers: authHeaders() })
      if (res.ok) setProviders(await res.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  async function handleTest(name) {
    setTesting(name)
    setTestResult(null)
    try {
      const res = await fetch(`${API_V1}/providers/${name}/test`, {
        method: 'POST',
        headers: authHeaders(),
      })
      const data = await res.json()
      setTestResult({ provider: name, ...data })
      // Refresh providers
      await loadProviders()
    } catch (e) {
      setTestResult({ provider: name, success: false, error: 'Request failed' })
    } finally {
      setTesting(null)
    }
  }

  async function handleToggle(name, activate) {
    try {
      await fetch(`${API_V1}/providers/${name}`, {
        method: 'PATCH',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: activate }),
      })
      await loadProviders()
    } catch (e) { console.error(e) }
  }

  async function handleDelete(name) {
    if (!confirm(`Delete provider "${name}"? This cannot be undone.`)) return
    try {
      const res = await fetch(`${API_V1}/providers/${name}`, { method: 'DELETE', headers: authHeaders() })
      if (res.ok || res.status === 204) await loadProviders()
    } catch (e) { console.error(e) }
  }

  async function handleReplaceKey(name) {
    const key = prompt(`Enter new API key for ${name}:`)
    if (!key || key.length < 8) return
    try {
      await fetch(`${API_V1}/providers/${name}`, {
        method: 'PATCH',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key }),
      })
      await loadProviders()
    } catch (e) { console.error(e) }
  }

  function handleCreated(provider) {
    setProviders(prev => {
      const idx = prev.findIndex(p => p.name === provider.name)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = provider
        return next
      }
      return [...prev, provider]
    })
    setShowAdd(false)
  }

  const healthyCount = providers.filter(p => p.status === 'healthy').length
  const configuredCount = providers.filter(p => p.is_configured).length
  const circuitOpen = providers.filter(p => p.circuit_state === 'open').length
  const totalRequests = providers.reduce((sum, p) => sum + p.total_requests, 0)

  return (
    <div>
      <div className="page-header">
        <h1>🤖 AI Gateway</h1>
        {isAdmin && (
          <button className="btn btn-primary" onClick={() => setShowAdd(!showAdd)}>
            {showAdd ? '✕ Cancel' : '+ Add Provider'}
          </button>
        )}
      </div>

      {showAdd && (
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <AddProviderForm onCreated={handleCreated} onCancel={() => setShowAdd(false)} />
        </div>
      )}

      {/* Summary */}
      <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="card-title">Providers</div>
          <div className="metric-value">{providers.length}</div>
        </div>
        <div className="card">
          <div className="card-title">Configured</div>
          <div className="metric-value" style={{ color: configuredCount > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
            {configuredCount}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Healthy</div>
          <div className="metric-value" style={{ color: healthyCount > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
            {healthyCount}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Total Requests</div>
          <div className="metric-value">{totalRequests}</div>
        </div>
      </div>

      {/* Test Result Banner */}
      {testResult && (
        <div style={{
          padding: 'var(--space-sm) var(--space-md)',
          marginBottom: 'var(--space-md)',
          background: testResult.success ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          border: `1px solid ${testResult.success ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
          borderRadius: 'var(--radius-sm)', fontSize: '13px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>
            {testResult.success ? '✅' : '❌'} {testResult.provider}: {testResult.success ? 'Connection successful' : testResult.error || 'Connection failed'}
          </span>
          <button onClick={() => setTestResult(null)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>✕</button>
        </div>
      )}

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
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: 'var(--space-md)' }}>
              Add an AI provider to enable intelligent incident analysis.
            </p>
            {isAdmin && (
              <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
                + Add Your First Provider
              </button>
            )}
          </div>
        ) : (
          providers.map(p => (
            <ProviderCard
              key={p.name}
              provider={p}
              isAdmin={isAdmin}
              onTest={handleTest}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onReplaceKey={handleReplaceKey}
              testing={testing}
            />
          ))
        )}
      </div>
    </div>
  )
}
