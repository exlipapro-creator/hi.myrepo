"""
hi.myrepo - Incident Engine

Incidents have explicit state governed by a state machine.
The UI does not own incident state — events do.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ErrorGroup,
    Event,
    Incident,
    IncidentAnalysis,
    IncidentStatus,
    IncidentStateTransition,
)


class IncidentCreate(BaseModel):
    """Data for creating a new incident."""
    project_id: uuid.UUID
    severity: str = "medium"
    title: Optional[str] = None
    summary: Optional[str] = None
    affected_service: Optional[str] = None
    affected_component: Optional[str] = None
    fingerprint: Optional[str] = None
    correlation_id: Optional[uuid.UUID] = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        valid = {"low", "medium", "high", "critical"}
        if v.lower() not in valid:
            raise ValueError(f"Invalid severity: {v}")
        return v.lower()


class IncidentEngine:
    """
    Manages incident lifecycle through the state machine.
    All state transitions are event-driven and auditable.
    """

    VALID_TRANSITIONS = IncidentStateTransition.TRANSITIONS

    async def create_incident(
        self,
        data: IncidentCreate,
        session: AsyncSession,
    ) -> Incident:
        """Create a new incident in DETECTED state."""
        incident = Incident(
            id=uuid.uuid4(),
            project_id=data.project_id,
            status=IncidentStatus.DETECTED,
            severity=data.severity,
            title=data.title,
            summary=data.summary,
            affected_service=data.affected_service,
            affected_component=data.affected_component,
            fingerprint=data.fingerprint,
            correlation_id=data.correlation_id,
            detected_at=datetime.now(timezone.utc),
        )
        session.add(incident)
        await session.flush()
        return incident

    async def transition(
        self,
        incident_id: uuid.UUID,
        target_status: str,
        session: AsyncSession,
        details: Optional[dict] = None,
    ) -> Incident:
        """
        Transition an incident to a new state.
        Validates the transition is allowed by the state machine.
        """
        # Fetch the current incident
        result = await session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        current_status = incident.status

        # Validate the transition
        if not IncidentStateTransition.can_transition(current_status, target_status):
            raise ValueError(
                f"Invalid transition: {current_status} → {target_status}. "
                f"Valid transitions from {current_status}: "
                f"{self.VALID_TRANSITIONS.get(current_status, [])}"
            )

        # Apply the transition
        incident.status = target_status
        incident.updated_at = datetime.now(timezone.utc)

        # Set resolved_at if transitioning to RESOLVED
        if target_status == IncidentStatus.RESOLVED:
            incident.resolved_at = datetime.now(timezone.utc)

        # Store transition details in metadata
        if details:
            incident.metadata_ = {**incident.metadata_, **details}

        await session.flush()
        return incident

    async def find_similar_incidents(
        self,
        fingerprint: str,
        project_id: Optional[uuid.UUID],
        session: AsyncSession,
        limit: int = 10,
    ) -> list[Incident]:
        """Search for historical incidents with the same fingerprint."""
        query = select(Incident).where(Incident.fingerprint == fingerprint)
        if project_id:
            query = query.where(Incident.project_id == project_id)
        query = query.order_by(Incident.detected_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_incident_with_context(
        self,
        incident_id: uuid.UUID,
        session: AsyncSession,
    ) -> Optional[Incident]:
        """Fetch an incident with its related events and analyses."""
        result = await session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        return result.scalar_one_or_none()

    async def get_incidents_by_project(
        self,
        project_id: uuid.UUID,
        session: AsyncSession,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        """Retrieve incidents for a project with optional status filtering."""
        query = select(Incident).where(Incident.project_id == project_id)
        if status:
            query = query.where(Incident.status == status)
        query = query.order_by(Incident.detected_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def update_incident_from_event(
        self,
        incident_id: uuid.UUID,
        event: Event,
        session: AsyncSession,
    ) -> Incident:
        """
        Update incident state based on incoming events.
        This is the event-driven state mutation — not UI-driven.
        """
        result = await session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        # Update based on event type
        if event.event_type == "DEPLOYMENT_SUCCEEDED":
            # Deployment correlation evidence
            incident.metadata_ = {
                **incident.metadata_,
                "recent_deployment": {
                    "event_id": str(event.id),
                    "payload": event.payload,
                    "timestamp": event.occurred_at.isoformat(),
                },
            }
        elif event.event_type == "HEARTBEAT_FAILURE":
            incident.severity = self._escalate_severity(incident.severity)
            incident.metadata_ = {
                **incident.metadata_,
                "heartbeat_failure": True,
            }
        elif event.event_type == "AI_REQUEST_SUCCEEDED":
            # AI analysis completed — update confidence if available
            if "confidence" in event.payload:
                incident.confidence = event.payload["confidence"]
            if "root_cause" in event.payload:
                incident.root_cause = event.payload["root_cause"]

        incident.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return incident

    def _escalate_severity(self, current: str) -> str:
        """Escalate severity level."""
        levels = ["low", "medium", "high", "critical"]
        idx = levels.index(current) if current in levels else 1
        return levels[min(idx + 1, len(levels) - 1)]


# Global incident engine singleton
incident_engine = IncidentEngine()
