"""
hi.myrepo - Event Spine

The immutable event spine is the architectural core.
Everything becomes an event. Events are never mutated — only appended.
Every event is: immutable, timestamped, attributable, traceable,
replayable, idempotent, correlation-aware.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event


class EventEnvelope(BaseModel):
    """
    The universal event envelope.
    Every subsystem produces events in this format.
    """
    event_id: Optional[uuid.UUID] = None
    event_type: str = Field(..., min_length=1, max_length=100)
    occurred_at: datetime
    received_at: Optional[datetime] = None
    source: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=50)
    project_id: uuid.UUID
    environment: str = "production"
    correlation_id: Optional[uuid.UUID] = None
    trace_id: Optional[uuid.UUID] = None
    severity: Optional[str] = None
    schema_version: int = 1
    idempotency_key: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        valid_types = {
            "HEARTBEAT_SUCCESS", "HEARTBEAT_FAILURE", "HEARTBEAT_DEGRADED",
            "ERROR_DETECTED", "ERROR_GROUP_UPDATED",
            "DEPLOYMENT_STARTED", "DEPLOYMENT_SUCCEEDED", "DEPLOYMENT_FAILED",
            "DEPLOYMENT_ROLLED_BACK",
            "AI_REQUEST_STARTED", "AI_PROVIDER_FAILED", "AI_PROVIDER_CASCADED",
            "AI_REQUEST_SUCCEEDED",
            "INCIDENT_CREATED", "INCIDENT_UPDATED", "INCIDENT_ESCALATED",
            "INCIDENT_RESOLVED",
            "RUNBOOK_PROPOSED", "RUNBOOK_APPROVED", "RUNBOOK_STARTED",
            "RUNBOOK_SUCCEEDED", "RUNBOOK_FAILED",
            "VERIFICATION_STARTED", "VERIFICATION_SUCCEEDED", "VERIFICATION_FAILED",
        }
        if v not in valid_types:
            raise ValueError(f"Invalid event_type: {v}. Must be one of: {sorted(valid_types)}")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = {"low", "medium", "high", "critical"}
            if v.lower() not in valid:
                raise ValueError(f"Invalid severity: {v}. Must be one of: {sorted(valid)}")
            return v.lower()
        return v

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        valid = {"application", "heartbeat", "webhook", "system", "worker"}
        if v not in valid:
            raise ValueError(f"Invalid source_type: {v}. Must be one of: {sorted(valid)}")
        return v


class EventProcessor:
    """
    Processes and persists events with idempotency.
    Invalid events are never silently dropped.
    """

    def __init__(self):
        self._validators = {}

    async def process_event(
        self,
        envelope: EventEnvelope,
        session: AsyncSession,
    ) -> Event:
        """
        Validate, persist, and emit an event.
        Idempotency: duplicate idempotency_key → return existing event.
        """
        # Generate IDs if not provided
        if envelope.event_id is None:
            envelope.event_id = uuid.uuid4()
        if envelope.received_at is None:
            envelope.received_at = datetime.now(timezone.utc)
        if envelope.idempotency_key is None:
            envelope.idempotency_key = (
                f"{envelope.event_type}:{envelope.source}:"
                f"{envelope.project_id}:{envelope.occurred_at.isoformat()}"
            )

        # Check idempotency — do not duplicate
        existing = await self._check_idempotency(session, envelope.idempotency_key)
        if existing:
            return existing

        # Create the immutable event record
        event = Event(
            id=envelope.event_id,
            event_type=envelope.event_type,
            occurred_at=envelope.occurred_at,
            received_at=envelope.received_at,
            source=envelope.source,
            source_type=envelope.source_type,
            project_id=envelope.project_id,
            environment=envelope.environment,
            correlation_id=envelope.correlation_id,
            trace_id=envelope.trace_id,
            severity=envelope.severity,
            schema_version=envelope.schema_version,
            idempotency_key=envelope.idempotency_key,
            payload=envelope.payload,
            metadata_=envelope.metadata,
        )

        session.add(event)
        await session.flush()

        return event

    async def _check_idempotency(
        self, session: AsyncSession, idempotency_key: str
    ) -> Optional[Event]:
        """Check if an event with this idempotency key already exists."""
        result = await session.execute(
            select(Event).where(Event.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def get_events_by_correlation(
        self, session: AsyncSession, correlation_id: uuid.UUID
    ) -> list[Event]:
        """Retrieve all events sharing a correlation ID."""
        result = await session.execute(
            select(Event)
            .where(Event.correlation_id == correlation_id)
            .order_by(Event.received_at)
        )
        return list(result.scalars().all())

    async def get_events_by_project(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Retrieve events for a project with optional filtering."""
        query = select(Event).where(Event.project_id == project_id)
        if event_type:
            query = query.where(Event.event_type == event_type)
        query = query.order_by(Event.received_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


# Global event processor singleton
event_processor = EventProcessor()
