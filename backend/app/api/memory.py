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
from app.security.auth import TokenData, get_current_user, get_user_project_ids

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
    from app.security.auth import require_project_access
    # Verify user's org owns the project
    await require_project_access(req.project_id, user)
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
    project_id: Optional[uuid.UUID] = None,
    limit: int = Query(default=20, le=100),
    user: TokenData = Depends(get_current_user),
):
    """Search memory records."""
    # Scope to user's organization projects
    user_project_ids = await get_user_project_ids(user)
    if not user_project_ids:
        return {"records": [], "total": 0}

    # If specific project_id requested, verify access
    if project_id:
        from app.security.auth import require_project_access
        await require_project_access(project_id, user)
        scope_ids = [project_id]
    else:
        scope_ids = user_project_ids

    async with db_manager.get_session() as session:
        all_records = []
        for pid in scope_ids:
            if fingerprint:
                records = await memory_engine.search_by_fingerprint(
                    fingerprint, session, project_id=pid, limit=limit
                )
                all_records.extend(records)
            elif category:
                records = await memory_engine.search_by_category(
                    category, session, project_id=pid, limit=limit
                )
                all_records.extend(records)
            elif tags:
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                if tag_list:
                    records = await memory_engine.search_by_tags(
                        tag_list, session, project_id=pid, limit=limit
                    )
                    all_records.extend(records)

        # Deduplicate and limit
        seen_ids = set()
        records = []
        for r in all_records:
            if str(r.id) not in seen_ids:
                seen_ids.add(str(r.id))
                records.append(r)
        records = records[:limit]

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
    project_id: Optional[uuid.UUID] = None,
    limit: int = Query(default=5, le=20),
    user: TokenData = Depends(get_current_user),
):
    """Find similar historical incidents by fingerprint, scoped to project."""
    user_project_ids = await get_user_project_ids(user)
    if not user_project_ids:
        return {"similar_incidents": [], "count": 0}

    async with db_manager.get_session() as session:
        if project_id:
            results = await memory_engine.get_similar_incidents(
                fingerprint, session, project_id=project_id, limit=limit
            )
        else:
            results = await memory_engine.get_similar_incidents(
                fingerprint, session, project_id=user_project_ids[0], limit=limit
            )
        return {"similar_incidents": results, "count": len(results)}


@router.get("/resolutions/{fingerprint}")
async def get_resolution_history(
    fingerprint: str,
    project_id: Optional[uuid.UUID] = None,
    user: TokenData = Depends(get_current_user),
):
    """Get all historical resolutions for a given fingerprint, scoped to project."""
    user_project_ids = await get_user_project_ids(user)
    if not user_project_ids:
        return {"resolutions": [], "count": 0}

    async with db_manager.get_session() as session:
        if project_id:
            results = await memory_engine.get_resolution_history(
                fingerprint, session, project_id=project_id
            )
        else:
            results = await memory_engine.get_resolution_history(
                fingerprint, session, project_id=user_project_ids[0]
            )
        return {"resolutions": results, "count": len(results)}
