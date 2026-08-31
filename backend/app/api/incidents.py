"""
hi.myrepo - Incidents API

Incident management, state transitions, and analysis.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import db_manager
from app.database.models import (
    Incident,
    IncidentAnalysis,
    IncidentStatus,
    IncidentStateTransition,
)
from app.incidents.engine import IncidentCreate, incident_engine
from app.security.auth import TokenData, get_current_user

router = APIRouter()


class IncidentResponse(BaseModel):
    id: str
    project_id: str
    status: str
    severity: str
    title: str | None
    summary: str | None
    affected_service: str | None
    affected_component: str | None
    fingerprint: str | None
    confidence: float | None
    blast_radius: str | None
    root_cause: str | None
    detected_at: str
    resolved_at: str | None
    created_at: str


class IncidentTransitionRequest(BaseModel):
    target_status: str
    details: dict | None = None


class IncidentStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_severity: dict[str, int]


@router.post("", status_code=201)
async def create_incident(
    req: IncidentCreate,
    user: TokenData = Depends(get_current_user),
):
    """Create a new incident."""
    async with db_manager.get_session() as session:
        incident = await incident_engine.create_incident(req, session)
        return {
            "id": str(incident.id),
            "status": incident.status,
            "severity": incident.severity,
            "message": "Incident created",
        }


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    project_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(get_current_user),
):
    """List incidents with filtering."""
    async with db_manager.get_session() as session:
        query = select(Incident)

        if project_id:
            query = query.where(Incident.project_id == project_id)
        if status_filter:
            query = query.where(Incident.status == status_filter)
        if severity:
            query = query.where(Incident.severity == severity)

        query = query.order_by(Incident.detected_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        incidents = result.scalars().all()

        return [
            IncidentResponse(
                id=str(i.id),
                project_id=str(i.project_id),
                status=i.status,
                severity=i.severity,
                title=i.title,
                summary=i.summary,
                affected_service=i.affected_service,
                affected_component=i.affected_component,
                fingerprint=i.fingerprint,
                confidence=i.confidence,
                blast_radius=i.blast_radius,
                root_cause=i.root_cause,
                detected_at=i.detected_at.isoformat(),
                resolved_at=i.resolved_at.isoformat() if i.resolved_at else None,
                created_at=i.created_at.isoformat(),
            )
            for i in incidents
        ]


@router.get("/stats", response_model=IncidentStatsResponse)
async def incident_stats(
    project_id: uuid.UUID | None = None,
    user: TokenData = Depends(get_current_user),
):
    """Get incident statistics."""
    async with db_manager.get_session() as session:
        base = select(Incident)
        if project_id:
            base = base.where(Incident.project_id == project_id)

        total = (await session.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0

        # By status
        status_q = select(Incident.status, func.count()).group_by(Incident.status)
        if project_id:
            status_q = status_q.where(Incident.project_id == project_id)
        status_r = await session.execute(status_q)
        by_status = {row[0]: row[1] for row in status_r.all()}

        # By severity
        sev_q = select(Incident.severity, func.count()).group_by(Incident.severity)
        if project_id:
            sev_q = sev_q.where(Incident.project_id == project_id)
        sev_r = await session.execute(sev_q)
        by_severity = {row[0]: row[1] for row in sev_r.all()}

        return IncidentStatsResponse(
            total=total, by_status=by_status, by_severity=by_severity
        )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Get a single incident with full details."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        return IncidentResponse(
            id=str(incident.id),
            project_id=str(incident.project_id),
            status=incident.status,
            severity=incident.severity,
            title=incident.title,
            summary=incident.summary,
            affected_service=incident.affected_service,
            affected_component=incident.affected_component,
            fingerprint=incident.fingerprint,
            confidence=incident.confidence,
            blast_radius=incident.blast_radius,
            root_cause=incident.root_cause,
            detected_at=incident.detected_at.isoformat(),
            resolved_at=incident.resolved_at.isoformat() if incident.resolved_at else None,
            created_at=incident.created_at.isoformat(),
        )


@router.post("/{incident_id}/transition")
async def transition_incident(
    incident_id: uuid.UUID,
    req: IncidentTransitionRequest,
    user: TokenData = Depends(get_current_user),
):
    """Transition an incident to a new state."""
    async with db_manager.get_session() as session:
        try:
            incident = await incident_engine.transition(
                incident_id=incident_id,
                target_status=req.target_status,
                session=session,
                details=req.details,
            )
            return {
                "id": str(incident.id),
                "status": incident.status,
                "message": f"Transitioned to {req.target_status}",
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.get("/{incident_id}/analysis")
async def get_incident_analysis(
    incident_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Get council analysis for an incident."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(IncidentAnalysis)
            .where(IncidentAnalysis.incident_id == incident_id)
            .order_by(IncidentAnalysis.created_at.desc())
        )
        analyses = result.scalars().all()

        return [
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
        ]
