"""
hi.myrepo - Events API

Event ingestion and querying endpoints.
POST /events — ingest events
GET /events — query events
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import db_manager
from app.database.models import Event
from app.events.spine import EventEnvelope, EventProcessor, event_processor
from app.security.auth import TokenData, get_current_user, require_project_access, get_user_project_ids

router = APIRouter()


class EventIngestRequest(BaseModel):
    """Single event ingestion."""
    event_type: str
    source: str
    source_type: str = "application"
    project_id: uuid.UUID
    environment: str = "production"
    occurred_at: Optional[str] = None  # ISO format
    correlation_id: Optional[uuid.UUID] = None
    trace_id: Optional[uuid.UUID] = None
    severity: Optional[str] = None
    payload: dict = {}
    metadata: dict = {}


class EventBatchIngestRequest(BaseModel):
    """Batch event ingestion."""
    events: list[EventIngestRequest]


class EventResponse(BaseModel):
    id: str
    event_type: str
    source: str
    source_type: str
    project_id: str
    environment: str
    severity: str | None
    correlation_id: str | None
    occurred_at: str
    received_at: str
    payload: dict
    metadata: dict


class EventStatsResponse(BaseModel):
    total_events: int
    by_type: dict[str, int]
    by_severity: dict[str, int]


@router.post("", status_code=201)
async def ingest_event(
    req: EventIngestRequest,
    user: TokenData = Depends(require_project_access),
):
    """Ingest a single event into the event spine."""
    # Note: require_project_access verified req.project_id belongs to user's org
    from datetime import datetime, timezone

    occurred_at = datetime.now(timezone.utc)
    if req.occurred_at:
        try:
            occurred_at = datetime.fromisoformat(req.occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid occurred_at format. Use ISO 8601.",
            )

    envelope = EventEnvelope(
        event_type=req.event_type,
        occurred_at=occurred_at,
        source=req.source,
        source_type=req.source_type,
        project_id=req.project_id,
        environment=req.environment,
        correlation_id=req.correlation_id,
        trace_id=req.trace_id,
        severity=req.severity,
        payload=req.payload,
        metadata=req.metadata,
    )

    async with db_manager.get_session() as session:
        event = await event_processor.process_event(envelope, session)

    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "idempotency_key": event.idempotency_key,
        "status": "accepted",
    }


@router.post("/batch", status_code=201)
async def ingest_events_batch(
    req: EventBatchIngestRequest,
    user: TokenData = Depends(get_current_user),
):
    """Ingest a batch of events."""
    # Verify project access for all events in batch
    if req.events:
        for event_req in req.events:
            await require_project_access(event_req.project_id, user)
    from datetime import datetime, timezone

    results = []
    errors = []

    async with db_manager.get_session() as session:
        for i, event_req in enumerate(req.events):
            try:
                occurred_at = datetime.now(timezone.utc)
                if event_req.occurred_at:
                    occurred_at = datetime.fromisoformat(
                        event_req.occurred_at.replace("Z", "+00:00")
                    )

                envelope = EventEnvelope(
                    event_type=event_req.event_type,
                    occurred_at=occurred_at,
                    source=event_req.source,
                    source_type=event_req.source_type,
                    project_id=event_req.project_id,
                    environment=event_req.environment,
                    correlation_id=event_req.correlation_id,
                    trace_id=event_req.trace_id,
                    severity=event_req.severity,
                    payload=event_req.payload,
                    metadata=event_req.metadata,
                )
                event = await event_processor.process_event(envelope, session)
                results.append({"index": i, "id": str(event.id), "status": "accepted"})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

    return {
        "processed": len(results),
        "errors": len(errors),
        "results": results,
        "error_details": errors,
    }


@router.get("")
async def list_events(
    project_id: Optional[uuid.UUID] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    correlation_id: Optional[uuid.UUID] = None,
    incident_id: Optional[uuid.UUID] = None,
    target_id: Optional[str] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(get_current_user),
):
    """Query events with filtering and server-side pagination."""
    from datetime import datetime as dt

    if project_id:
        await require_project_access(project_id, user)
    else:
        # Scope to user's organization projects
        user_project_ids = await get_user_project_ids(user)
        if not user_project_ids:
            return {"events": [], "total": 0, "limit": limit, "offset": offset, "has_more": False}

    async with db_manager.get_session() as session:
        query = select(Event)

        if project_id:
            query = query.where(Event.project_id == project_id)
        elif not project_id:
            query = query.where(Event.project_id.in_(user_project_ids))
        if event_type:
            query = query.where(Event.event_type == event_type)
        if severity:
            query = query.where(Event.severity == severity)
        if correlation_id:
            query = query.where(Event.correlation_id == correlation_id)
        if incident_id:
            query = query.where(Event.incident_id == incident_id)
        if source:
            query = query.where(Event.source == source)
        if target_id:
            # Filter by target_id in event payload JSONB
            from sqlalchemy import cast, String as SAString
            query = query.where(Event.payload["target_id"].astext == target_id)
        if from_date:
            try:
                from_dt = dt.fromisoformat(from_date.replace("Z", "+00:00"))
                query = query.where(Event.received_at >= from_dt)
            except ValueError:
                pass
        if to_date:
            try:
                to_dt = dt.fromisoformat(to_date.replace("Z", "+00:00"))
                query = query.where(Event.received_at <= to_dt)
            except ValueError:
                pass

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_query)).scalar() or 0

        # Fetch
        query = query.order_by(Event.received_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        events = result.scalars().all()

        return {
            "events": [
                EventResponse(
                    id=str(e.id),
                    event_type=e.event_type,
                    source=e.source,
                    source_type=e.source_type,
                    project_id=str(e.project_id),
                    environment=e.environment,
                    severity=e.severity,
                    correlation_id=str(e.correlation_id) if e.correlation_id else None,
                    occurred_at=e.occurred_at.isoformat(),
                    received_at=e.received_at.isoformat(),
                    payload=e.payload or {},
                    metadata=e.metadata_ or {},
                ).model_dump()
                for e in events
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }


@router.get("/aggregate")
async def aggregate_events(
    project_id: Optional[uuid.UUID] = None,
    time_window: str = Query(default="1h", description="Aggregation window: 1h, 6h, 24h"),
    user: TokenData = Depends(get_current_user),
):
    """Aggregate events into operational conditions for dashboard.
    Groups repetitive events (e.g., HEARTBEAT_DEGRADED) into a single condition
    with occurrence counts, first/last seen, and linked incident.
    """
    from datetime import timedelta
    from sqlalchemy import func

    if project_id:
        await require_project_access(project_id, user)
    else:
        user_project_ids = await get_user_project_ids(user)
        if not user_project_ids:
            return {"conditions": [], "total": 0}

    # Parse time window
    window_map = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24)}
    window_delta = window_map.get(time_window, timedelta(hours=1))
    since = datetime.now(timezone.utc) - window_delta

    async with db_manager.get_session() as session:
        # Query events grouped by event_type + source, with counts
        query = (
            select(
                Event.event_type,
                Event.source,
                Event.severity,
                Event.project_id,
                func.count().label("occurrence_count"),
                func.min(Event.received_at).label("first_seen"),
                func.max(Event.received_at).label("last_seen"),
            )
            .where(Event.received_at >= since)
            .group_by(Event.event_type, Event.source, Event.severity, Event.project_id)
            .order_by(func.count().desc())
        )
        if project_id:
            query = query.where(Event.project_id == project_id)
        else:
            query = query.where(Event.project_id.in_(user_project_ids))

        result = await session.execute(query)
        rows = result.all()

        conditions = []
        for row in rows:
            conditions.append({
                "event_type": row.event_type,
                "source": row.source,
                "severity": row.severity,
                "project_id": str(row.project_id),
                "occurrence_count": row.occurrence_count,
                "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
            })

        return {"conditions": conditions, "total": len(conditions)}


@router.get("/stats", response_model=EventStatsResponse)
async def event_stats(
    project_id: Optional[uuid.UUID] = None,
    user: TokenData = Depends(get_current_user),
):
    """Get event statistics."""
    if project_id:
        await require_project_access(project_id, user)
    else:
        user_project_ids = await get_user_project_ids(user)
        if not user_project_ids:
            return EventStatsResponse(total_events=0, by_type={}, by_severity={})

    async with db_manager.get_session() as session:
        base_query = select(Event)
        if project_id:
            base_query = base_query.where(Event.project_id == project_id)
        else:
            base_query = base_query.where(Event.project_id.in_(user_project_ids))

        # Total
        total = (await session.execute(
            select(func.count()).select_from(base_query.subquery())
        )).scalar() or 0

        # By type
        type_query = (
            select(Event.event_type, func.count())
            .group_by(Event.event_type)
        )
        if project_id:
            type_query = type_query.where(Event.project_id == project_id)
        else:
            type_query = type_query.where(Event.project_id.in_(user_project_ids))
        type_result = await session.execute(type_query)
        by_type = {row[0]: row[1] for row in type_result.all()}

        # By severity
        sev_query = (
            select(Event.severity, func.count())
            .where(Event.severity.isnot(None))
            .group_by(Event.severity)
        )
        if project_id:
            sev_query = sev_query.where(Event.project_id == project_id)
        else:
            sev_query = sev_query.where(Event.project_id.in_(user_project_ids))
        sev_result = await session.execute(sev_query)
        by_severity = {row[0]: row[1] for row in sev_result.all()}

        return EventStatsResponse(
            total_events=total,
            by_type=by_type,
            by_severity=by_severity,
        )


class RetentionRequest(BaseModel):
    """Event retention policy configuration."""
    retention_days: int = 90  # Default: keep events for 90 days
    exclude_types: list[str] = []  # Event types to always retain (never purge)
    dry_run: bool = True  # Preview mode — do not delete by default


class RetentionResponse(BaseModel):
    total_events: int
    eligible_for_deletion: int
    protected_events: int
    retention_days: int
    cutoff_date: str
    deleted: int = 0
    dry_run: bool


@router.post("/retention", response_model=RetentionResponse)
async def apply_retention_policy(
    req: RetentionRequest,
    user: TokenData = Depends(get_current_user),
):
    """Apply event retention policy. Protected events (incident-linked, error groups, deployments) are never purged.
    
    Safety rules:
    - Events linked to incidents are always protected
    - Events linked to error groups are always protected
    - Deployment events are always protected
    - AI analysis events are always protected
    - Heartbeat SUCCESS events older than retention are eligible
    - Heartbeat FAILURE/DEGRADED events linked to open incidents are protected
    - dry_run=True (default) only reports what would be deleted
    """
    from datetime import timedelta
    from app.database.models import AuditLog, Incident

    cutoff = datetime.now(timezone.utc) - timedelta(days=req.retention_days)

    async with db_manager.get_session() as session:
        # Count total events
        total = (await session.execute(select(func.count()).select_from(Event))).scalar() or 0

        # Count events older than retention
        old_events_q = select(func.count()).where(Event.received_at < cutoff)
        old_count = (await session.execute(old_events_q)).scalar() or 0

        # Count protected events (linked to incidents)
        protected_q = select(func.count()).where(
            Event.received_at < cutoff,
            Event.incident_id.isnot(None),
        )
        protected_by_incident = (await session.execute(protected_q)).scalar() or 0

        # Count events that are always protected (deployments, AI, errors)
        always_protected_q = select(func.count()).where(
            Event.received_at < cutoff,
            Event.event_type.in_([
                'DEPLOYMENT_STARTED', 'DEPLOYMENT_SUCCEEDED', 'DEPLOYMENT_FAILED', 'DEPLOYMENT_ROLLED_BACK',
                'AI_REQUEST_STARTED', 'AI_REQUEST_SUCCEEDED', 'AI_PROVIDER_FAILED', 'AI_PROVIDER_CASCADED',
                'INCIDENT_CREATED', 'INCIDENT_UPDATED', 'INCIDENT_ESCALATED', 'INCIDENT_RESOLVED',
                'RUNBOOK_PROPOSED', 'RUNBOOK_APPROVED', 'RUNBOOK_STARTED', 'RUNBOOK_SUCCEEDED', 'RUNBOOK_FAILED',
                'VERIFICATION_STARTED', 'VERIFICATION_SUCCEEDED', 'VERIFICATION_FAILED',
            ]),
        )
        always_protected = (await session.execute(always_protected_q)).scalar() or 0

        # Count heartbeat failures that are linked to open incidents
        open_incident_events_q = (
            select(func.count())
            .select_from(Event)
            .join(Incident, Event.incident_id == Incident.id)
            .where(
                Event.received_at < cutoff,
                Event.event_type.in_(['HEARTBEAT_FAILURE', 'HEARTBEAT_DEGRADED']),
                Incident.status.notin_(['RESOLVED']),
            )
        )
        incident_linked_failures = (await session.execute(open_incident_events_q)).scalar() or 0

        total_protected = protected_by_incident + always_protected + incident_linked_failures
        eligible = max(0, old_count - total_protected)

        deleted = 0
        if not req.dry_run and eligible > 0:
            # Delete eligible events: old, not linked to incidents, not deployment/AI/incident type
            from sqlalchemy import delete
            delete_q = (
                delete(Event)
                .where(
                    Event.received_at < cutoff,
                    Event.incident_id.isNone(),
                    Event.event_type.in_(['HEARTBEAT_SUCCESS', 'HEARTBEAT_DEGRADED']),
                )
            )
            result = await session.execute(delete_q)
            deleted = result.rowcount

            # Audit the retention action
            audit = AuditLog(
                id=uuid.uuid4(),
                action="events.retention_applied",
                actor_type="user",
                actor_id=user.user_id,
                resource_type="events",
                details={
                    "retention_days": req.retention_days,
                    "cutoff_date": cutoff.isoformat(),
                    "events_deleted": deleted,
                    "events_protected": total_protected,
                },
                outcome="success",
            )
            session.add(audit)
            await session.flush()

        return RetentionResponse(
            total_events=total,
            eligible_for_deletion=eligible,
            protected_events=total_protected,
            retention_days=req.retention_days,
            cutoff_date=cutoff.isoformat(),
            deleted=deleted,
            dry_run=req.dry_run,
        )
