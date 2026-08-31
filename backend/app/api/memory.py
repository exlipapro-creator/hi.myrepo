"""
hi.myrepo - Memory API

Institutional memory: search past incidents, resolutions, and patterns.
The system builds operational memory over time.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.database.connection import db_manager
from app.memory.engine import MemoryCreate, memory_engine
from app.security.auth import TokenData, get_current_user

router = APIRouter()


class MemoryRecordResponse(BaseModel):
    id: str
    incident_id: str | None
    fingerprint: str | None
    category: str
    title: str
    summary: str
    root_cause: str | None
    resolution: str | None
    runbook_code: str | None
    success: bool
    was_autonomous: bool
    created_at: str


@router.post("", status_code=201)
async def create_memory_record(
    req: MemoryCreate,
    user: TokenData = Depends(get_current_user),
):
    """Record a new memory entry."""
    async with db_manager.get_session() as session:
        record = await memory_engine.record_outcome(req, session)
        return {
            "id": str(record.id),
            "status": "created",
            "category": record.category,
        }


@router.get("/search")
async def search_memory(
    fingerprint: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,  # comma-separated
    limit: int = Query(default=20, le=100),
    user: TokenData = Depends(get_current_user),
):
    """Search memory records."""
    async with db_manager.get_session() as session:
        records = []

        if fingerprint:
            records = await memory_engine.search_by_fingerprint(
                fingerprint, session, limit
            )
        elif category:
            records = await memory_engine.search_by_category(
                category, session, limit=limit
            )
        elif tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                records = await memory_engine.search_by_tags(
                    tag_list, session, limit=limit
                )

        return {
            "records": [
                MemoryRecordResponse(
                    id=str(r.id),
                    incident_id=str(r.incident_id) if r.incident_id else None,
                    fingerprint=r.fingerprint,
                    category=r.category,
                    title=r.title,
                    summary=r.summary,
                    root_cause=r.root_cause,
                    resolution=r.resolution,
                    runbook_code=r.runbook_code,
                    success=r.success,
                    was_autonomous=r.was_autonomous,
                    created_at=r.created_at.isoformat() if r.created_at else None,
                ).model_dump()
                for r in records
            ],
            "total": len(records),
        }


@router.get("/similar/{fingerprint}")
async def get_similar_incidents(
    fingerprint: str,
    limit: int = Query(default=5, le=20),
    user: TokenData = Depends(get_current_user),
):
    """Find similar historical incidents by fingerprint."""
    async with db_manager.get_session() as session:
        results = await memory_engine.get_similar_incidents(
            fingerprint, session, limit
        )
        return {"similar_incidents": results, "count": len(results)}


@router.get("/resolutions/{fingerprint}")
async def get_resolution_history(
    fingerprint: str,
    user: TokenData = Depends(get_current_user),
):
    """Get all historical resolutions for a given fingerprint."""
    async with db_manager.get_session() as session:
        results = await memory_engine.get_resolution_history(fingerprint, session)
        return {"resolutions": results, "count": len(results)}
