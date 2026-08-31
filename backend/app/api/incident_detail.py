"""
hi.myrepo - Incident Detail API

Full incident investigation context:
- Timeline of events
- Council analysis
- Runbook executions
- Verification results
- Memory records
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import (
    AuditLog,
    ErrorGroup,
    Event,
    Incident,
    IncidentAnalysis,
    RunbookExecution,
    VerificationRun,
)
from app.security.auth import TokenData, get_current_user

router = APIRouter()


@router.get("/{incident_id}/full")
async def get_incident_full(
    incident_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """
    Get a complete incident investigation context.

    Returns:
    - Incident details
    - Timeline of related events
    - Error groups
    - Council analyses
    - Runbook executions
    - Verification runs
    - Audit trail
    """
    async with db_manager.get_session() as session:
        # Get the incident
        result = await session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Get related events
        events_result = await session.execute(
            select(Event)
            .where(Event.project_id == incident.project_id)
            .where(
                (Event.correlation_id == incident.correlation_id) |
                (Event.fingerprint == incident.fingerprint) if incident.fingerprint
                else (Event.correlation_id == incident.correlation_id)
            )
            .order_by(Event.received_at.desc())
            .limit(100)
        )
        events = events_result.scalars().all()

        # Get error groups
        eg_result = await session.execute(
            select(ErrorGroup).where(
                ErrorGroup.project_id == incident.project_id,
                ErrorGroup.fingerprint == incident.fingerprint,
            ) if incident.fingerprint else select(ErrorGroup).where(
                ErrorGroup.id == uuid.uuid4()  # no match
            )
        )
        error_groups = eg_result.scalars().all()

        # Get council analyses
        analysis_result = await session.execute(
            select(IncidentAnalysis)
            .where(IncidentAnalysis.incident_id == incident_id)
            .order_by(IncidentAnalysis.created_at.desc())
        )
        analyses = analysis_result.scalars().all()

        # Get runbook executions
        exec_result = await session.execute(
            select(RunbookExecution)
            .where(RunbookExecution.incident_id == incident_id)
            .order_by(RunbookExecution.created_at)
        )
        executions = exec_result.scalars().all()

        # Get verification runs
        ver_result = await session.execute(
            select(VerificationRun)
            .where(VerificationRun.incident_id == incident_id)
            .order_by(VerificationRun.created_at)
        )
        verifications = ver_result.scalars().all()

        # Get audit trail
        audit_result = await session.execute(
            select(AuditLog)
            .where(AuditLog.incident_id == incident_id)
            .order_by(AuditLog.created_at)
        )
        audit_logs = audit_result.scalars().all()

        # Build timeline
        timeline = []
        timeline.append({
            "type": "incident_detected",
            "timestamp": incident.detected_at.isoformat(),
            "details": {
                "severity": incident.severity,
                "status": incident.status,
                "title": incident.title,
            },
        })

        for e in events:
            timeline.append({
                "type": "event",
                "timestamp": e.received_at.isoformat(),
                "details": {
                    "event_type": e.event_type,
                    "source": e.source,
                    "severity": e.severity,
                },
            })

        for a in analyses:
            timeline.append({
                "type": "council_analysis",
                "timestamp": a.created_at.isoformat(),
                "details": {
                    "analysis_type": a.analysis_type,
                    "root_cause": a.root_cause,
                    "confidence": a.confidence,
                    "recommended_action": a.recommended_action,
                },
            })

        for ex in executions:
            timeline.append({
                "type": "runbook_execution",
                "timestamp": ex.created_at.isoformat(),
                "details": {
                    "status": ex.status,
                    "approved_by": ex.approved_by,
                    "error_message": ex.error_message,
                },
            })

        for v in verifications:
            timeline.append({
                "type": "verification",
                "timestamp": v.created_at.isoformat(),
                "details": {
                    "status": v.status,
                    "checks_passed": v.checks_passed,
                    "checks_failed": v.checks_failed,
                    "success": v.success,
                },
            })

        # Sort timeline by timestamp
        timeline.sort(key=lambda x: x["timestamp"])

        if incident.resolved_at:
            timeline.append({
                "type": "incident_resolved",
                "timestamp": incident.resolved_at.isoformat(),
                "details": {"status": incident.status},
            })

        return {
            "incident": {
                "id": str(incident.id),
                "project_id": str(incident.project_id),
                "status": incident.status,
                "severity": incident.severity,
                "title": incident.title,
                "summary": incident.summary,
                "affected_service": incident.affected_service,
                "affected_component": incident.affected_component,
                "fingerprint": incident.fingerprint,
                "correlation_id": str(incident.correlation_id) if incident.correlation_id else None,
                "confidence": incident.confidence,
                "blast_radius": incident.blast_radius,
                "root_cause": incident.root_cause,
                "recommended_runbook_id": str(incident.recommended_runbook_id) if incident.recommended_runbook_id else None,
                "detected_at": incident.detected_at.isoformat(),
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
                "created_at": incident.created_at.isoformat(),
            },
            "timeline": timeline,
            "error_groups": [
                {
                    "id": str(eg.id),
                    "fingerprint": eg.fingerprint,
                    "error_type": eg.error_type,
                    "error_message": eg.error_message,
                    "occurrence_count": eg.occurrence_count,
                    "route": eg.route,
                    "first_seen": eg.first_seen.isoformat(),
                    "last_seen": eg.last_seen.isoformat(),
                }
                for eg in error_groups
            ],
            "council_analyses": [
                {
                    "id": str(a.id),
                    "analysis_type": a.analysis_type,
                    "root_cause": a.root_cause,
                    "confidence": a.confidence,
                    "evidence": a.evidence,
                    "alternative_hypotheses": a.alternative_hypotheses,
                    "blast_radius_assessment": a.blast_radius_assessment,
                    "recommended_action": a.recommended_action,
                    "risk_assessment": a.risk_assessment,
                    "required_verification": a.required_verification,
                    "council_rounds_used": a.council_rounds_used,
                    "council_budget_exceeded": a.council_budget_exceeded,
                    "created_at": a.created_at.isoformat(),
                }
                for a in analyses
            ],
            "runbook_executions": [
                {
                    "id": str(ex.id),
                    "runbook_id": str(ex.runbook_id),
                    "status": ex.status,
                    "approved_by": ex.approved_by,
                    "approved_at": ex.approved_at.isoformat() if ex.approved_at else None,
                    "started_at": ex.started_at.isoformat() if ex.started_at else None,
                    "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
                    "execution_log": ex.execution_log,
                    "error_message": ex.error_message,
                    "rollback_performed": ex.rollback_performed,
                    "created_at": ex.created_at.isoformat(),
                }
                for ex in executions
            ],
            "verification_runs": [
                {
                    "id": str(v.id),
                    "status": v.status,
                    "verification_type": v.verification_type,
                    "checks_performed": v.checks_performed,
                    "checks_passed": v.checks_passed,
                    "checks_failed": v.checks_failed,
                    "success": v.success,
                    "error_message": v.error_message,
                    "started_at": v.started_at.isoformat() if v.started_at else None,
                    "completed_at": v.completed_at.isoformat() if v.completed_at else None,
                }
                for v in verifications
            ],
            "audit_trail": [
                {
                    "id": str(al.id),
                    "action": al.action,
                    "actor_type": al.actor_type,
                    "actor_id": al.actor_id,
                    "details": al.details,
                    "outcome": al.outcome,
                    "created_at": al.created_at.isoformat(),
                }
                for al in audit_logs
            ],
        }
