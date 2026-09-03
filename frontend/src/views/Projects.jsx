import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const AUTONOMY_LEVELS = [
  { value: 0, label: 'OBSERVE', desc: 'Watch only — no actions taken' },
  { value: 1, label: 'RECOMMEND', desc: 'Suggest actions, require approval' },
  { value: 2, label: 'AUTOPILOT', desc: 'Execute approved runbooks automatically' },
]

const ENVIRONMENTS = ['production', 'staging', 'development']

function CreateProjectForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({
    name: '',
    slug: '',
    description: '',
    repository_url: '',
    environment: 'production',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function updateField(key, value) {
    setForm(prev => {
      const next = { ...prev, [key]: value }
      // Auto-generate slug from name
      if (key === 'name' && !prev.slugManuallyEdited) {
        next.slug = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
      }
      return next
    })
  }

  function handleSlugChange(value) {
    setForm(prev => ({ ...prev, slug: value, slugManuallyEdited: true }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (!form.name.trim() || !form.slug.trim()) {
      setError('Name and slug are required')
      return
    }
    setLoading(true)
    try {
      const res = await fetch(`${API}/projects`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim(),
          slug: form.slug.trim(),
          description: form.description.trim() || null,
          repository_url: form.repository_url.trim() || null,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Failed to create project')
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

  const labelStyle = {
    display: 'block', fontSize: '12px', color: 'var(--text-muted)',
    marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em',
  }

  return (
    <div className="card" style={{ maxWidth: '600px' }}>
      <div className="card-header">
        <span className="card-title">CREATE PROJECT</span>
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
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-md)' }}>
          <div>
            <label style={labelStyle}>Project Name *</label>
            <input
              type="text" required value={form.name}
              onChange={e => updateField('name', e.target.value)}
              placeholder="My SaaS"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Slug *</label>
            <input
              type="text" required value={form.slug}
              onChange={e => handleSlugChange(e.target.value)}
              placeholder="my-saas"
              style={{ ...inputStyle, fontFamily: 'var(--font-mono)' }}
            />
          </div>
        </div>
        <div style={{ marginTop: 'var(--space-md)' }}>
          <label style={labelStyle}>Description</label>
          <input
            type="text" value={form.description}
            onChange={e => updateField('description', e.target.value)}
            placeholder="What does this project do?"
            style={inputStyle}
          />
        </div>
        <div style={{ marginTop: 'var(--space-md)' }}>
          <label style={labelStyle}>Repository URL</label>
          <input
            type="url" value={form.repository_url}
            onChange={e => updateField('repository_url', e.target.value)}
            placeholder="https://github.com/org/repo"
            style={inputStyle}
          />
        </div>
        <div style={{ marginTop: 'var(--space-md)' }}>
          <label style={labelStyle}>Initial Environment</label>
          <select
            value={form.environment}
            onChange={e => updateField('environment', e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}
          >
            {ENVIRONMENTS.map(env => (
              <option key={env} value={env}>{env}</option>
            ))}
          </select>
        </div>
        <div style={{ marginTop: 'var(--space-lg)', display: 'flex', gap: 'var(--space-sm)' }}>
          <button type="submit" disabled={loading} className="btn btn-primary" style={{ flex: 1 }}>
            {loading ? 'Creating...' : 'Create Project'}
          </button>
          <button type="button" onClick={onCancel} className="btn" style={{ color: 'var(--text-muted)' }}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

function ProjectCard({ project, health, onClick }) {
  const healthColor = {
    healthy: 'var(--accent-green)',
    degraded: 'var(--accent-yellow)',
    unhealthy: 'var(--accent-red)',
    unknown: 'var(--text-muted)',
  }[health?.health || 'unknown']

  const isMonitoring = project.monitoring_status === 'active'

  return (
    <div
      className="card"
      onClick={() => onClick(project)}
      style={{ cursor: 'pointer', transition: 'border-color 0.15s' }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-blue)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border-primary)'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>{project.name}</h3>
          <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{project.slug}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
          <span className="mono" style={{
            fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
            background: isMonitoring ? 'rgba(34, 197, 94, 0.1)' : 'rgba(107, 114, 128, 0.1)',
            color: isMonitoring ? 'var(--accent-green)' : 'var(--text-muted)',
            border: `1px solid ${isMonitoring ? 'rgba(34, 197, 94, 0.3)' : 'rgba(107, 114, 128, 0.2)'}`,
          }}>
            {isMonitoring ? '◉ MONITORING' : '○ STOPPED'}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{
              width: '8px', height: '8px', borderRadius: '50%',
              background: healthColor, display: 'inline-block',
            }} />
            <span className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {health ? health.health.toUpperCase() : 'LOADING'}
            </span>
          </div>
        </div>
      </div>
      {project.description && (
        <p style={{ marginTop: 'var(--space-sm)', color: 'var(--text-secondary)', fontSize: '13px' }}>
          {project.description}
        </p>
      )}
      {health && (
        <div style={{
          marginTop: 'var(--space-md)', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 'var(--space-sm)', padding: 'var(--space-sm)',
          background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)',
        }}>
          <div style={{ textAlign: 'center' }}>
            <div className="metric-label">Events</div>
            <div className="mono" style={{ fontSize: '14px', fontWeight: 600 }}>{health.total_events}</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="metric-label">Incidents</div>
            <div className="mono" style={{
              fontSize: '14px', fontWeight: 600,
              color: health.active_incidents > 0 ? 'var(--accent-orange)' : 'var(--text-primary)',
            }}>{health.active_incidents}</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="metric-label">Deploys</div>
            <div className="mono" style={{ fontSize: '14px', fontWeight: 600 }}>{health.total_deployments}</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="metric-label">Error Rate</div>
            <div className="mono" style={{
              fontSize: '14px', fontWeight: 600,
              color: health.recent_error_rate > 0.1 ? 'var(--accent-red)' : 'var(--text-primary)',
            }}>{(health.recent_error_rate * 100).toFixed(1)}%</div>
          </div>
        </div>
      )}
      <div style={{ marginTop: 'var(--space-sm)', display: 'flex', gap: 'var(--space-md)' }}>
        <div>
          <div className="metric-label">Autonomy</div>
          <div className="mono" style={{ fontSize: '12px' }}>
            {AUTONOMY_LEVELS[project.autonomy_level]?.label || `Level ${project.autonomy_level}`}
          </div>
        </div>
        {project.repository_url && (
          <div>
            <div className="metric-label">Repository</div>
            <span className="mono" style={{ fontSize: '12px', color: 'var(--accent-blue)' }}>
              {project.repository_url.replace('https://github.com/', '').replace(/\/$/, '')}
            </span>
          </div>
        )}
        <div>
          <div className="metric-label">Created</div>
          <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            {project.created_at ? formatDistanceToNow(new Date(project.created_at), { addSuffix: true }) : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}

function MonitoredTargets({ projectId }) {
  const [targets, setTargets] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', url: '', interval_seconds: 60 })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => { loadTargets() }, [projectId])

  async function loadTargets() {
    setLoading(true)
    try {
      const res = await fetch(`${API}/monitored-targets?project_id=${projectId}`, { headers: authHeaders() })
      if (res.ok) setTargets(await res.json())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  async function handleAdd(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const res = await fetch(`${API}/monitored-targets?project_id=${projectId}`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, name: form.name, url: form.url, interval_seconds: parseInt(form.interval_seconds) || 60 }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to add target'); return }
      setTargets(prev => [data, ...prev])
      setForm({ name: '', url: '', interval_seconds: 60 })
      setShowAdd(false)
    } catch (err) { setError('Connection failed') }
    finally { setSaving(false) }
  }

  async function handleEdit(target) {
    setEditing(target)
    setForm({ name: target.name, url: target.url, interval_seconds: target.interval_seconds })
    setShowAdd(true)
  }

  async function handleUpdate(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const res = await fetch(`${API}/monitored-targets/${editing.id}`, {
        method: 'PATCH',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: form.name, url: form.url, interval_seconds: parseInt(form.interval_seconds) || 60 }),
      })
      if (!res.ok) { const d = await res.json(); setError(d.detail || 'Failed'); return }
      setTargets(prev => prev.map(t => t.id === editing.id ? { ...t, name: form.name, url: form.url, interval_seconds: parseInt(form.interval_seconds) } : t))
      setShowAdd(false)
      setEditing(null)
    } catch (err) { setError('Connection failed') }
    finally { setSaving(false) }
  }

  async function handleDelete(target) {
    if (!confirm(`Delete target "${target.name}"?`)) return
    try {
      const res = await fetch(`${API}/monitored-targets/${target.id}`, { method: 'DELETE', headers: authHeaders() })
      if (res.ok || res.status === 204) setTargets(prev => prev.filter(t => t.id !== target.id))
    } catch (e) { console.error(e) }
  }

  const inputStyle = {
    width: '100%', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
    borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text-primary)',
    fontSize: '13px', outline: 'none', fontFamily: 'inherit',
  }
  const labelStyle = { display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }

  return (
    <div className="card" style={{ marginTop: 'var(--space-md)' }}>
      <div className="card-header">
        <span className="card-title">MONITORED TARGETS</span>
        <button className="btn" onClick={() => { setShowAdd(!showAdd); setEditing(null); setForm({ name: '', url: '', interval_seconds: 60 }) }} style={{ fontSize: '11px', color: 'var(--accent-blue)' }}>
          {showAdd ? '\u2715 Cancel' : '+ Add Target'}
        </button>
      </div>

      {showAdd && (
        <form onSubmit={editing ? handleUpdate : handleAdd} style={{ padding: 'var(--space-sm)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-md)' }}>
          {error && <div style={{ padding: '6px 10px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 'var(--radius-sm)', color: 'var(--accent-red)', fontSize: '12px', marginBottom: 'var(--space-sm)' }}>{error}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr 1fr', gap: 'var(--space-sm)' }}>
            <div>
              <label style={labelStyle}>Name</label>
              <input type="text" required value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="Production API" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>URL</label>
              <input type="url" required value={form.url} onChange={e => setForm(p => ({ ...p, url: e.target.value }))} placeholder="https://api.example.com/health" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Interval (s)</label>
              <input type="number" min="10" max="3600" value={form.interval_seconds} onChange={e => setForm(p => ({ ...p, interval_seconds: e.target.value }))} style={inputStyle} />
            </div>
          </div>
          <div style={{ marginTop: 'var(--space-sm)', display: 'flex', gap: 'var(--space-sm)' }}>
            <button type="submit" disabled={saving} className="btn btn-primary" style={{ fontSize: '12px' }}>
              {saving ? 'Saving...' : editing ? 'Update Target' : 'Add Target'}
            </button>
            <button type="button" onClick={() => { setShowAdd(false); setEditing(null) }} className="btn" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Cancel</button>
          </div>
        </form>
      )}

      {loading ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-md)', fontSize: '13px' }}>Loading targets...</div>
      ) : targets.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-lg)', fontSize: '13px' }}>
          No targets configured. Add a target to begin monitoring.
        </div>
      ) : (
        <table>
          <thead>
            <tr><th>Name</th><th>URL</th><th>Interval</th><th>Status</th><th>Latency</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {targets.map(t => (
              <tr key={t.id}>
                <td style={{ fontWeight: 500 }}>{t.name}</td>
                <td className="mono" style={{ fontSize: '12px', color: 'var(--accent-blue)', maxWidth: '250px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.url}</td>
                <td className="mono" style={{ fontSize: '12px' }}>{t.interval_seconds}s</td>
                <td>
                  <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: t.is_active && !t.is_degraded ? 'rgba(34,197,94,0.1)' : t.is_degraded ? 'rgba(245,158,11,0.1)' : 'rgba(107,114,128,0.1)', color: t.is_active && !t.is_degraded ? 'var(--accent-green)' : t.is_degraded ? 'var(--accent-yellow)' : 'var(--text-muted)', border: `1px solid ${t.is_active && !t.is_degraded ? 'rgba(34,197,94,0.3)' : t.is_degraded ? 'rgba(245,158,11,0.3)' : 'rgba(107,114,128,0.2)'}` }}>
                    {t.is_active ? (t.is_degraded ? 'DEGRADED' : 'ACTIVE') : 'DISABLED'}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: '12px' }}>{t.last_latency_ms != null ? `${t.last_latency_ms.toFixed(0)}ms` : '\u2014'}</td>
                <td>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button onClick={() => handleEdit(t)} style={{ background: 'none', border: 'none', color: 'var(--accent-blue)', cursor: 'pointer', fontSize: '11px' }}>Edit</button>
                    <button onClick={() => handleDelete(t)} style={{ background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer', fontSize: '11px' }}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function ProjectDetail({ project, health, onBack, onMonitoringChange }) {
  const [monitoringLoading, setMonitoringLoading] = useState(false)
  const isMonitoring = project.monitoring_status === 'active'

  async function handleToggleMonitoring() {
    setMonitoringLoading(true)
    try {
      const action = isMonitoring ? 'stop' : 'start'
      const res = await fetch(`${API}/projects/${project.id}/monitoring/${action}`, {
        method: 'POST',
        headers: authHeaders(),
      })
      if (res.ok) {
        const data = await res.json()
        onMonitoringChange({
          ...project,
          monitoring_status: data.status,
          monitoring_started_at: data.started_at || project.monitoring_started_at,
          monitoring_stopped_at: data.stopped_at || project.monitoring_stopped_at,
        })
      }
    } catch (e) { console.error(e) }
    finally { setMonitoringLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <button
            onClick={onBack}
            style={{
              background: 'none', border: 'none', color: 'var(--accent-blue)',
              cursor: 'pointer', fontSize: '12px', padding: 0, marginBottom: '4px',
            }}
          >
            ← Back to Projects
          </button>
          <h1>
            {project.name}
            <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '14px', marginLeft: 'var(--space-sm)' }}>
              {project.slug}
            </span>
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
          <button
            className="btn"
            onClick={handleToggleMonitoring}
            disabled={monitoringLoading}
            style={{
              fontSize: '12px', fontWeight: 600,
              background: isMonitoring ? 'rgba(239, 68, 68, 0.1)' : 'rgba(34, 197, 94, 0.1)',
              border: `1px solid ${isMonitoring ? 'rgba(239, 68, 68, 0.3)' : 'rgba(34, 197, 94, 0.3)'}`,
              color: isMonitoring ? 'var(--accent-red)' : 'var(--accent-green)',
            }}
          >
            {monitoringLoading ? '...' : isMonitoring ? '⏹ Stop Monitoring' : '▶ Start Monitoring'}
          </button>
          <span className="mono" style={{
            fontSize: '11px', padding: '3px 8px', borderRadius: '4px',
            background: isMonitoring ? 'rgba(34, 197, 94, 0.1)' : 'rgba(107, 114, 128, 0.1)',
            color: isMonitoring ? 'var(--accent-green)' : 'var(--text-muted)',
            border: `1px solid ${isMonitoring ? 'rgba(34, 197, 94, 0.3)' : 'rgba(107, 114, 128, 0.2)'}`,
          }}>
            {isMonitoring ? '◉ MONITORING ACTIVE' : '○ MONITORING STOPPED'}
          </span>
        </div>
      </div>

      {project.description && (
        <div className="card" style={{ marginBottom: 'var(--space-md)' }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>{project.description}</p>
        </div>
      )}

      {/* Health Overview */}
      <div className="bento-grid" style={{ marginBottom: 'var(--space-md)' }}>
        <div className="card">
          <div className="card-title">Health</div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px',
          }}>
            <span style={{
              width: '12px', height: '12px', borderRadius: '50%',
              background: {
                healthy: 'var(--accent-green)',
                degraded: 'var(--accent-yellow)',
                unhealthy: 'var(--accent-red)',
              }[health?.health] || 'var(--text-muted)',
            }} />
            <span style={{ fontSize: '16px', fontWeight: 600, textTransform: 'uppercase' }}>
              {health?.health || 'unknown'}
            </span>
          </div>
        </div>
        <div className="card">
          <div className="card-title">Events</div>
          <div className="metric-value">{health?.total_events || 0}</div>
        </div>
        <div className="card">
          <div className="card-title">Active Incidents</div>
          <div className="metric-value" style={{
            color: (health?.active_incidents || 0) > 0 ? 'var(--accent-orange)' : 'var(--text-primary)',
          }}>
            {health?.active_incidents || 0}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Error Rate</div>
          <div className="metric-value" style={{
            color: (health?.recent_error_rate || 0) > 0.1 ? 'var(--accent-red)' : 'var(--text-primary)',
          }}>
            {health ? `${(health.recent_error_rate * 100).toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>

      {/* Configuration */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-md)' }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">CONFIGURATION</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className="metric-label">Autonomy Level</span>
              <span className="mono" style={{ fontSize: '13px' }}>
                {AUTONOMY_LEVELS[project.autonomy_level]?.label || `Level ${project.autonomy_level}`}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className="metric-label">Organization</span>
              <span className="mono" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                {project.organization_id.slice(0, 8)}…
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className="metric-label">Created</span>
              <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                {project.created_at ? new Date(project.created_at).toLocaleString() : '—'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className="metric-label">Updated</span>
              <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                {project.updated_at ? new Date(project.updated_at).toLocaleString() : '—'}
              </span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">DEPENDENCIES</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
            {health ? (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="metric-label">Healthy Dependencies</span>
                  <span className="mono" style={{ fontSize: '13px', color: 'var(--accent-green)' }}>
                    {health.healthy_dependencies}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="metric-label">Unhealthy Dependencies</span>
                  <span className="mono" style={{
                    fontSize: '13px',
                    color: health.unhealthy_dependencies > 0 ? 'var(--accent-red)' : 'var(--text-muted)',
                  }}>
                    {health.unhealthy_dependencies}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="metric-label">Deployments</span>
                  <span className="mono" style={{ fontSize: '13px' }}>
                    {health.total_deployments}
                  </span>
                </div>
              </>
            ) : (
              <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-md)' }}>
                Loading health data...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Monitored Targets */}
      <MonitoredTargets projectId={project.id} />

      {/* Repository */}
      {project.repository_url && (
        <div className="card" style={{ marginTop: 'var(--space-md)' }}>
          <div className="card-header">
            <span className="card-title">REPOSITORY</span>
          </div>
          <a
            href={project.repository_url}
            target="_blank"
            rel="noopener"
            style={{ color: 'var(--accent-blue)', fontSize: '14px', textDecoration: 'none' }}
          >
            {project.repository_url}
          </a>
        </div>
      )}
    </div>
  )
}

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [healthMap, setHealthMap] = useState({})
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedProject, setSelectedProject] = useState(null)
  const [selectedHealth, setSelectedHealth] = useState(null)

  useEffect(() => { loadProjects() }, [])

  async function loadProjects() {
    setLoading(true)
    try {
      const res = await fetch(`${API}/projects`, { headers: authHeaders() })
      if (res.ok) {
        const projs = await res.json()
        setProjects(projs)

        // Load health for each project
        const healthPromises = projs.map(async (p) => {
          try {
            const hRes = await fetch(`${API}/projects/${p.id}/health`, { headers: authHeaders() })
            if (hRes.ok) return { id: p.id, health: await hRes.json() }
          } catch {}
          return { id: p.id, health: null }
        })
        const results = await Promise.all(healthPromises)
        const map = {}
        results.forEach(r => { map[r.id] = r.health })
        setHealthMap(map)
      }
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  function handleCreated(project) {
    setProjects(prev => [project, ...prev])
    setShowCreate(false)
    // Load health for new project
    fetch(`${API}/projects/${project.id}/health`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(h => { if (h) setHealthMap(prev => ({ ...prev, [project.id]: h })) })
      .catch(() => {})
  }

  function handleSelectProject(project) {
    setSelectedProject(project)
    setSelectedHealth(healthMap[project.id] || null)
    // Fetch fresh health
    fetch(`${API}/projects/${project.id}/health`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(h => { if (h) setSelectedHealth(h) })
      .catch(() => {})
  }

  function handleMonitoringChange(updatedProject) {
    setSelectedProject(updatedProject)
    setProjects(prev => prev.map(p => p.id === updatedProject.id ? updatedProject : p))
  }

  // Project detail view
  if (selectedProject) {
    return (
      <ProjectDetail
        project={selectedProject}
        health={selectedHealth}
        onBack={() => { setSelectedProject(null); setSelectedHealth(null) }}
        onMonitoringChange={handleMonitoringChange}
      />
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>📦 Projects</h1>
        <button
          className="btn btn-primary"
          onClick={() => setShowCreate(!showCreate)}
        >
          {showCreate ? '✕ Cancel' : '+ Create Project'}
        </button>
      </div>

      {showCreate && (
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <CreateProjectForm
            onCreated={handleCreated}
            onCancel={() => setShowCreate(false)}
          />
        </div>
      )}

      {loading ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 'var(--space-lg)' }}>
          Loading projects...
        </div>
      ) : projects.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 'var(--space-xl)' }}>
          <div style={{ fontSize: '32px', marginBottom: 'var(--space-md)' }}>📦</div>
          <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: 'var(--space-sm)' }}>
            No projects yet
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: 'var(--space-lg)' }}>
            Create your first project to begin observing your systems.
          </p>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            + Create Your First Project
          </button>
        </div>
      ) : (
        <div className="bento-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))' }}>
          {projects.map(p => (
            <ProjectCard
              key={p.id}
              project={p}
              health={healthMap[p.id]}
              onClick={handleSelectProject}
            />
          ))}
        </div>
      )}
    </div>
  )
}
