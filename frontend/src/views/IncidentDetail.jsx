import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { AlertTriangle, Radio, Bot, Play, CheckCircle, Check, ArrowLeft, Shield, RefreshCw, Loader } from 'lucide-react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function TimelineEntry({ entry }) {
  const iconComponents = {
    incident_detected: AlertTriangle,
    event: Radio,
    council_analysis: Bot,
    runbook_execution: Play,
    verification: CheckCircle,
    incident_resolved: Check,
  }

  const colors = {
    incident_detected: 'var(--accent-orange)',
    event: 'var(--accent-cyan)',
    council_analysis: 'var(--accent-purple)',
    runbook_execution: 'var(--accent-blue)',
    verification: 'var(--accent-green)',
    incident_resolved: 'var(--accent-green)',
  }

  const IconComponent = iconComponents[entry.type]

  return (
    <div style={{
      display: 'flex', gap: 'var(--space-md)', padding: 'var(--space-sm) 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      <div style={{ minWidth: '28px', textAlign: 'center', color: colors[entry.type] || 'var(--text-muted)' }}>
        {IconComponent ? <IconComponent size={18} /> : <span style={{ fontSize: '14px' }}>•</span>}
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
  const [actionLoading, setActionLoading] = useState('')
  const [actionMessage, setActionMessage] = useState('')

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

  async function handleInvestigate() {
    setActionLoading('investigate')
    setActionMessage('')
    try {
      const res = await fetch(`${API}/incidents/${id}/investigate`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      })
      if (res.ok) {
        const result = await res.json()
        setActionMessage(`Investigation complete — confidence: ${(result.confidence * 100).toFixed(0)}%`)
        await loadIncident()
      } else {
        const err = await res.json().catch(() => ({}))
        setActionMessage(`Investigation failed: ${err.detail || res.status}`)
      }
    } catch (e) {
      setActionMessage('Network error during investigation')
    } finally {
      setActionLoading('')
    }
  }

  async function handleApprove(executionId) {
    setActionLoading(executionId)
    setActionMessage('')
    try {
      const res = await fetch(`${API}/runbooks/${executionId}/approve`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by: 'operator' }),
      })
      if (res.ok) {
        setActionMessage('Execution approved')
        await loadIncident()
      } else {
        const err = await res.json().catch(() => ({}))
        setActionMessage(`Approval failed: ${err.detail || res.status}`)
      }
    } catch (e) {
      setActionMessage('Network error during approval')
    } finally {
      setActionLoading('')
    }
  }

  async function handleExecute(executionId) {
    setActionLoading(executionId)
    setActionMessage('')
    try {
      const res = await fetch(`${API}/runbooks/executions/${executionId}/execute`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (res.ok) {
        const result = await res.json()
        setActionMessage(result.success ? `Execution succeeded: ${result.message}` : `Execution failed: ${result.message}`)
        await loadIncident()
      } else {
        const err = await res.json().catch(() => ({}))
        setActionMessage(`Execution failed: ${err.detail || res.status}`)
      }
    } catch (e) {
      setActionMessage('Network error during execution')
    } finally {
      setActionLoading('')
    }
  }

  async function handleTransition(targetStatus) {
    setActionLoading(`transition-${targetStatus}`)
    setActionMessage('')
    try {
      const res = await fetch(`${API}/incidents/${id}/transition`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_status: targetStatus }),
      })
      if (res.ok) {
        setActionMessage(`Transitioned to ${targetStatus}`)
        await loadIncident()
      } else {
        const err = await res.json().catch(() => ({}))
        setActionMessage(`Transition failed: ${err.detail || res.status}`)
      }
    } catch (e) {
      setActionMessage('Network error during transition')
    } finally {
      setActionLoading('')
    }
  }

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: 'var(--space-lg)' }}>Loading...</div>
  if (error) return <div style={{ color: 'var(--accent-red)', padding: 'var(--space-lg)' }}>{error}</div>
  if (!data) return null

  const { incident: inc, timeline, error_groups, council_analyses, runbook_executions, verification_runs, audit_trail, memory_records } = data

  // Determine valid transitions from current state
  const validTransitions = {
    DETECTED: ['TRIAGING'],
    TRIAGING: ['INVESTIGATING'],
    INVESTIGATING: ['DIAGNOSED', 'TRIAGING'],
    DIAGNOSED: ['AWAITING_ACTION'],
    AWAITING_ACTION: ['REMEDIATING', 'ESCALATED'],
    REMEDIATING: ['VERIFYING', 'REMEDIATION_FAILED'],
    VERIFYING: ['RESOLVED', 'REMEDIATION_FAILED'],
    REMEDIATION_FAILED: ['ESCALATED'],
    RESOLVED: [],
    ESCALATED: [],
  }

  const pendingExecutions = runbook_executions.filter(e => e.status === 'PENDING')
  const approvedExecutions = runbook_executions.filter(e => e.status === 'APPROVED')

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/incidents" style={{ color: 'var(--accent-blue)', textDecoration: 'none', fontSize: '12px' }}>
            <ArrowLeft size={14} style={{ verticalAlign: 'middle' }} /> Back to Incidents
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

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 'var(--space-sm)', marginBottom: 'var(--space-lg)', flexWrap: 'wrap' }}>
        {/* Investigate button — only when no analyses exist yet */}
        {council_analyses.length === 0 && inc.status !== 'RESOLVED' && (
          <button
            className="btn btn-primary"
            onClick={handleInvestigate}
            disabled={!!actionLoading}
            style={{ fontSize: '12px' }}
          >
            {actionLoading === 'investigate' ? <Loader size={14} style={{ marginRight: '4px', animation: 'spin 1s linear infinite' }} /> : <Bot size={14} style={{ marginRight: '4px' }} />}
            Run Investigation
          </button>
        )}

        {/* State transition buttons */}
        {(validTransitions[inc.status] || []).map(target => (
          <button
            key={target}
            className="btn"
            onClick={() => handleTransition(target)}
            disabled={!!actionLoading}
            style={{ fontSize: '12px' }}
          >
            {actionLoading === `transition-${target}` ? <Loader size={14} style={{ marginRight: '4px', animation: 'spin 1s linear infinite' }} /> : <ArrowLeft size={14} style={{ marginRight: '4px', transform: 'rotate(180deg)' }} />}
            Transition → {target}
          </button>
        ))}

        {/* Refresh */}
        <button className="btn" onClick={loadIncident} disabled={loading} style={{ fontSize: '12px' }}>
          <RefreshCw size={14} style={{ marginRight: '4px' }} /> Refresh
        </button>
      </div>

      {/* Action message */}
      {actionMessage && (
        <div className="card" style={{
          marginBottom: 'var(--space-md)', padding: 'var(--space-sm)',
          borderColor: actionMessage.includes('failed') ? 'var(--accent-red)' : 'var(--accent-green)',
          fontSize: '13px',
        }}>
          {actionMessage}
        </div>
      )}

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

      {/* Pending Approvals */}
      {pendingExecutions.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--space-lg)', borderColor: 'var(--accent-orange)' }}>
          <div className="card-header">
            <span className="card-title" style={{ color: 'var(--accent-orange)' }}>PENDING APPROVALS</span>
          </div>
          {pendingExecutions.map(ex => (
            <div key={ex.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
              <div>
                <span className="mono" style={{ fontSize: '12px' }}>Execution {ex.id.slice(0, 8)}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginLeft: '8px' }}>
                  Created {ex.created_at ? formatDistanceToNow(new Date(ex.created_at), { addSuffix: true }) : ''}
                </span>
              </div>
              <button
                className="btn btn-primary"
                onClick={() => handleApprove(ex.id)}
                disabled={!!actionLoading}
                style={{ fontSize: '12px', padding: '4px 12px' }}
              >
                {actionLoading === ex.id ? <Loader size={14} /> : <><Check size={14} style={{ marginRight: '4px' }} />Approve</>}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Approved Executions Ready to Run */}
      {approvedExecutions.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--space-lg)', borderColor: 'var(--accent-blue)' }}>
          <div className="card-header">
            <span className="card-title" style={{ color: 'var(--accent-blue)' }}>READY TO EXECUTE</span>
          </div>
          {approvedExecutions.map(ex => (
            <div key={ex.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
              <div>
                <span className="mono" style={{ fontSize: '12px' }}>Execution {ex.id.slice(0, 8)}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginLeft: '8px' }}>
                  Approved by {ex.approved_by || '—'}
                </span>
              </div>
              <button
                className="btn btn-primary"
                onClick={() => handleExecute(ex.id)}
                disabled={!!actionLoading}
                style={{ fontSize: '12px', padding: '4px 12px' }}
              >
                {actionLoading === ex.id ? <Loader size={14} /> : <><Play size={14} style={{ marginRight: '4px' }} />Execute</>}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Timeline + Sidebar */}
      <div className="detail-layout" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-md)' }}>
        {/* Timeline */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">TIMELINE ({timeline.length} entries)</span>
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
                  {a.evidence?.agents && (
                    <div style={{ marginTop: '4px' }}>
                      {a.evidence.agents.map((agent, i) => (
                        <div key={i} style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                          <span className="mono" style={{ color: 'var(--accent-purple)' }}>{agent.role}</span>
                          {' '}(conf: {(agent.confidence * 100).toFixed(0)}%)
                          {agent.challenges?.length > 0 && (
                            <span style={{ color: 'var(--accent-orange)' }}> · {agent.challenges.length} challenge(s)</span>
                          )}
                        </div>
                      ))}
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
                    <span className={`status-badge ${ex.status === 'SUCCEEDED' ? 'healthy' : ex.status === 'FAILED' ? 'unhealthy' : 'degraded'}`} style={{ fontSize: '11px' }}>
                      {ex.status}
                    </span>
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

          {/* Historical Memory */}
          {memory_records && memory_records.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">HISTORICAL MEMORY</span>
                <span className="mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                  {memory_records.length} similar
                </span>
              </div>
              {memory_records.map(m => (
                <div key={m.id} style={{ padding: 'var(--space-sm)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span className="mono" style={{ fontSize: '11px', color: 'var(--accent-purple)' }}>{m.category}</span>
                    <span className={`status-badge ${m.success ? 'healthy' : 'unhealthy'}`} style={{ fontSize: '10px' }}>
                      {m.success ? 'resolved' : 'failed'}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', marginTop: '2px' }}>{m.title}</div>
                  {m.resolution && (
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Resolution: {m.resolution.slice(0, 80)}
                    </div>
                  )}
                  {m.runbook_code && (
                    <div className="mono" style={{ fontSize: '10px', color: 'var(--accent-blue)', marginTop: '2px' }}>
                      {m.runbook_code}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
