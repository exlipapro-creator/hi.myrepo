import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'

const API = '/api/v1'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function TimelineEntry({ entry }) {
  const icons = {
    incident_detected: '🔥',
    event: '📡',
    council_analysis: '🤖',
    runbook_execution: '📋',
    verification: '✅',
    incident_resolved: '🟢',
  }

  const colors = {
    incident_detected: 'var(--accent-orange)',
    event: 'var(--accent-cyan)',
    council_analysis: 'var(--accent-purple)',
    runbook_execution: 'var(--accent-blue)',
    verification: 'var(--accent-green)',
    incident_resolved: 'var(--accent-green)',
  }

  return (
    <div style={{
      display: 'flex', gap: 'var(--space-md)', padding: 'var(--space-sm) 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      <div style={{ fontSize: '18px', minWidth: '28px', textAlign: 'center' }}>
        {icons[entry.type] || '📌'}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{
            fontSize: '13px', fontWeight: 600,
            color: colors[entry.type] || 'var(--text-primary)',
          }}>
            {entry.type.replace(/_/g, ' ').toUpperCase()}
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
            {entry.timestamp ? formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true }) : ''}
          </span>
        </div>
        <div style={{ marginTop: '4px', fontSize: '12px', color: 'var(--text-secondary)' }}>
          {entry.details?.event_type && <span className="mono" style={{ color: 'var(--accent-cyan)' }}>{entry.details.event_type} </span>}
          {entry.details?.source && <span style={{ color: 'var(--text-muted)' }}>from {entry.details.source} </span>}
          {entry.details?.confidence != null && <span className="mono">confidence: {(entry.details.confidence * 100).toFixed(0)}% </span>}
          {entry.details?.status && <span className="mono">{entry.details.status} </span>}
          {entry.details?.root_cause && <span style={{ display: 'block', marginTop: '2px' }}>Root cause: {entry.details.root_cause}</span>}
          {entry.details?.recommended_action && <span style={{ display: 'block', marginTop: '2px', color: 'var(--accent-blue)' }}>→ {entry.details.recommended_action}</span>}
        </div>
      </div>
    </div>
  )
}

export default function IncidentDetail() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => { loadIncident() }, [id])

  async function loadIncident() {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API}/incidents/${id}/full`, { headers: authHeaders() })
      if (!res.ok) {
        setError(`Incident not found (${res.status})`)
        return
      }
      setData(await res.json())
    } catch (e) {
      setError('Failed to load incident')
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: 'var(--space-lg)' }}>Loading...</div>
  if (error) return <div style={{ color: 'var(--accent-red)', padding: 'var(--space-lg)' }}>{error}</div>
  if (!data) return null

  const { incident: inc, timeline, error_groups, council_analyses, runbook_executions, verification_runs, audit_trail } = data

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/incidents" style={{ color: 'var(--accent-blue)', textDecoration: 'none', fontSize: '12px' }}>
            ← Back to Incidents
          </Link>
          <h1 style={{ marginTop: '4px' }}>
            <span className={`severity-badge ${inc.severity}`} style={{ marginRight: 'var(--space-sm)' }}>{inc.severity}</span>
            {inc.title || `Incident ${inc.id.slice(0, 8)}`}
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-md)', alignItems: 'center' }}>
          <span className={`status-badge ${inc.status === 'RESOLVED' ? 'healthy' : inc.status === 'ESCALATED' ? 'unhealthy' : 'degraded'}`}>
            {inc.status}
          </span>
          {inc.confidence != null && (
            <span className="mono" style={{ fontSize: '14px' }}>
              {(inc.confidence * 100).toFixed(0)}% confidence
            </span>
          )}
        </div>
      </div>

      {/* Summary cards */}
      <div className="bento-grid" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="card-title">Service</div>
          <div className="mono" style={{ fontSize: '14px' }}>{inc.affected_service || '—'}</div>
        </div>
        <div className="card">
          <div className="card-title">Component</div>
          <div className="mono" style={{ fontSize: '14px' }}>{inc.affected_component || '—'}</div>
        </div>
        <div className="card">
          <div className="card-title">Blast Radius</div>
          <span className={`severity-badge ${inc.blast_radius || 'low'}`}>{inc.blast_radius || 'unknown'}</span>
        </div>
        <div className="card">
          <div className="card-title">Fingerprint</div>
          <div className="mono" style={{ fontSize: '12px', wordBreak: 'break-all' }}>{inc.fingerprint || '—'}</div>
        </div>
      </div>

      {/* Root Cause */}
      {inc.root_cause && (
        <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="card-header">
            <span className="card-title">ROOT CAUSE</span>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>{inc.root_cause}</p>
        </div>
      )}

      {/* Timeline + Sidebar */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-md)' }}>
        {/* Timeline */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">TIMELINE ({timeline.length} events)</span>
          </div>
          <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
            {timeline.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', padding: 'var(--space-md)', textAlign: 'center' }}>
                No timeline events
              </div>
            ) : (
              timeline.map((entry, i) => <TimelineEntry key={i} entry={entry} />)
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
          {/* Error Groups */}
          {error_groups.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">ERROR GROUPS</span>
              </div>
              {error_groups.map(eg => (
                <div key={eg.id} style={{ padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div className="mono" style={{ fontSize: '12px', color: 'var(--accent-cyan)' }}>{eg.error_type}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{eg.error_message?.slice(0, 100)}</div>
                  <div className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {eg.occurrence_count} occurrences · {eg.route || 'unknown route'}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Council Analyses */}
          {council_analyses.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">COUNCIL ANALYSIS</span>
              </div>
              {council_analyses.map(a => (
                <div key={a.id} style={{ padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span className="mono" style={{ fontSize: '11px', color: 'var(--accent-purple)' }}>{a.analysis_type}</span>
                    <span className="mono" style={{ fontSize: '11px' }}>{(a.confidence * 100).toFixed(0)}%</span>
                  </div>
                  {a.root_cause && (
                    <div style={{ fontSize: '12px', marginTop: '4px' }}>{a.root_cause.slice(0, 150)}</div>
                  )}
                  {a.recommended_action && (
                    <div style={{ fontSize: '12px', color: 'var(--accent-blue)', marginTop: '4px' }}>
                      → {a.recommended_action.slice(0, 100)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Runbook Executions */}
          {runbook_executions.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">RUNBOOK EXECUTIONS</span>
              </div>
              {runbook_executions.map(ex => (
                <div key={ex.id} style={{ padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span className="mono" style={{ fontSize: '12px' }}>{ex.status}</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {ex.approved_by || '—'}
                    </span>
                  </div>
                  {ex.error_message && (
                    <div style={{ fontSize: '11px', color: 'var(--accent-red)', marginTop: '4px' }}>
                      {ex.error_message.slice(0, 100)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Verification Runs */}
          {verification_runs.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">VERIFICATION</span>
              </div>
              {verification_runs.map(v => (
                <div key={v.id} style={{ padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span className={`status-badge ${v.success ? 'healthy' : 'unhealthy'}`}>
                      {v.status}
                    </span>
                    <span className="mono" style={{ fontSize: '11px' }}>
                      {v.checks_passed}/{v.checks_passed + v.checks_failed} checks
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Audit Trail */}
          {audit_trail.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">AUDIT TRAIL</span>
              </div>
              {audit_trail.map(al => (
                <div key={al.id} style={{ padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div className="mono" style={{ fontSize: '11px', color: 'var(--accent-cyan)' }}>{al.action}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {al.actor_type} · {al.outcome || '—'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
