"""
hi.myrepo - Incident Memory

The system retains previous incidents, fingerprints, diagnoses, deployments,
remediation, verification results, and postmortems.

When a new incident appears:
    Current incident → fingerprint → historical search → similar incidents
    → previous remediation → evidence supplied to council

The system effectively builds operational memory.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MemoryRecord


class MemoryCreate(BaseModel):
    """Data for creating a memory record."""
    project_id: uuid.UUID
    incident_id: Optional[uuid.UUID] = None
    fingerprint: Optional[str] = None
    category: str  # incident, resolution, postmortem, pattern
    title: str
    summary: str
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    runbook_code: Optional[str] = None
    confidence_at_resolution: Optional[float] = None
    was_autonomous: bool = False
    success: bool = True
    tags: list[str] = Field(default_factory=list)


class MemorySearchResult(BaseModel):
    """Result of a memory search."""
    records: list[dict]
    total_count: int
    search_criteria: dict


class MemoryEngine:
    """
    Manages institutional memory.
    The system learns from outcomes and builds knowledge over time.
    """

    async def record_outcome(
        self,
        data: MemoryCreate,
        session: AsyncSession,
    ) -> MemoryRecord:
        """Record the outcome of an incident or remediation."""
        record = MemoryRecord(
            id=uuid.uuid4(),
            project_id=data.project_id,
            incident_id=data.incident_id,
            fingerprint=data.fingerprint,
            category=data.category,
            title=data.title,
            summary=data.summary,
            root_cause=data.root_cause,
            resolution=data.resolution,
            runbook_code=data.runbook_code,
            confidence_at_resolution=data.confidence_at_resolution,
            was_autonomous=data.was_autonomous,
            success=data.success,
            tags=data.tags,
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.flush()
        return record

    async def search_by_fingerprint(
        self,
        fingerprint: str,
        session: AsyncSession,
        project_id: Optional[uuid.UUID] = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Search memory for records matching a fingerprint, scoped to project."""
        query = select(MemoryRecord).where(MemoryRecord.fingerprint == fingerprint)
        if project_id is not None:
            query = query.where(MemoryRecord.project_id == project_id)
        query = query.order_by(MemoryRecord.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def search_by_category(
        self,
        category: str,
        session: AsyncSession,
        project_id: Optional[uuid.UUID] = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Search memory by category, scoped to project."""
        query = select(MemoryRecord).where(MemoryRecord.category == category)
        if project_id is not None:
            query = query.where(MemoryRecord.project_id == project_id)
        query = query.order_by(MemoryRecord.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def search_by_tags(
        self,
        tags: list[str],
        session: AsyncSession,
        project_id: Optional[uuid.UUID] = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Search memory by tags, scoped to project."""
        query = select(MemoryRecord)
        if project_id is not None:
            query = query.where(MemoryRecord.project_id == project_id)
        # PostgreSQL JSONB array contains check
        for tag in tags:
            query = query.where(MemoryRecord.tags.op("@>")(f'["{tag}"]'))
        query = query.order_by(MemoryRecord.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_similar_incidents(
        self,
        fingerprint: str,
        session: AsyncSession,
        project_id: Optional[uuid.UUID] = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Find similar historical incidents based on fingerprint, scoped to project.
        Returns evidence for the council.
        """
        records = await self.search_by_fingerprint(fingerprint, session, project_id=project_id, limit=limit)
        return [
            {
                "id": str(r.id),
                "incident_id": str(r.incident_id) if r.incident_id else None,
                "title": r.title,
                "summary": r.summary,
                "root_cause": r.root_cause,
                "resolution": r.resolution,
                "runbook_code": r.runbook_code,
                "success": r.success,
                "was_autonomous": r.was_autonomous,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

    async def get_resolution_history(
        self,
        fingerprint: str,
        session: AsyncSession,
        project_id: Optional[uuid.UUID] = None,
    ) -> list[dict]:
        """Get all resolutions for a given fingerprint, scoped to project."""
        query = (
            select(MemoryRecord)
            .where(MemoryRecord.fingerprint == fingerprint)
            .where(MemoryRecord.category == "resolution")
        )
        if project_id is not None:
            query = query.where(MemoryRecord.project_id == project_id)
        query = query.order_by(MemoryRecord.created_at.desc()).limit(10)
        result = await session.execute(query)
        records = result.scalars().all()
        return [
            {
                "resolution": r.resolution,
                "runbook_code": r.runbook_code,
                "success": r.success,
                "confidence": r.confidence_at_resolution,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]


# Global memory engine singleton
memory_engine = MemoryEngine()
