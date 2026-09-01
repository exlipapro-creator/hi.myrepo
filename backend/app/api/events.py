"""
hi.myrepo - Events API

Event ingestion and querying endpoints.
POST /events — ingest events
GET /events — query events
"""
import uuid
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
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(get_current_user),
):
    """Query events with filtering."""
    if project_id:
        await require_project_access(project_id, user)
    else:
        # Scope to user's organization projects
        user_project_ids = await get_user_project_ids(user)
        if not user_project_ids:
            return {"events": [], "total": 0, "limit": limit, "offset": offset}

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
        }


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
