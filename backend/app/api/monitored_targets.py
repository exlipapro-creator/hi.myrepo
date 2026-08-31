"""
hi.myrepo - Monitored Targets API

CRUD for heartbeat monitoring targets.
The heartbeat worker reads these targets to know what to check.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import MonitoredTarget, Project
from app.security.auth import TokenData, get_current_user, require_project_access

router = APIRouter()


class MonitoredTargetCreate(BaseModel):
    project_id: uuid.UUID
    name: str
    url: str
    method: str = "GET"
    expected_status: int = 200
    timeout_seconds: int = 10
    interval_seconds: int = 60
    headers: dict = {}


class MonitoredTargetUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    expected_status: Optional[int] = None
    timeout_seconds: Optional[int] = None
    interval_seconds: Optional[int] = None
    is_active: Optional[bool] = None
    headers: Optional[dict] = None


class MonitoredTargetResponse(BaseModel):
    id: str
    project_id: str
    name: str
    url: str
    method: str
    expected_status: int
    timeout_seconds: int
    interval_seconds: int
    is_active: bool
    last_check_at: Optional[str]
    last_status: Optional[int]
    last_latency_ms: Optional[float]
    is_degraded: bool
    created_at: str


@router.post("", status_code=201)
async def create_target(
    req: MonitoredTargetCreate,
    user: TokenData = Depends(require_project_access),
):
    """Create a new monitored target."""
    # Validate URL against SSRF before storing
    from app.security.ssrf import ssrf_protector, SSRFError
    try:
        ssrf_protector.validate_url(req.url)
    except SSRFError as e:
        raise HTTPException(status_code=400, detail=f"URL validation failed: {e}")

    async with db_manager.get_session() as session:
        # Verify project exists
        result = await session.execute(
            select(Project).where(Project.id == req.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        target = MonitoredTarget(
            id=uuid.uuid4(),
            project_id=req.project_id,
            name=req.name,
            url=req.url,
            method=req.method,
            expected_status=req.expected_status,
            timeout_seconds=req.timeout_seconds,
            interval_seconds=req.interval_seconds,
            headers=req.headers,
        )
        session.add(target)
        await session.flush()

        return MonitoredTargetResponse(
            id=str(target.id),
            project_id=str(target.project_id),
            name=target.name,
            url=target.url,
            method=target.method,
            expected_status=target.expected_status,
            timeout_seconds=target.timeout_seconds,
            interval_seconds=target.interval_seconds,
            is_active=target.is_active,
            last_check_at=None,
            last_status=None,
            last_latency_ms=None,
            is_degraded=False,
            created_at=target.created_at.isoformat(),
        )


@router.get("")
async def list_targets(
    project_id: Optional[uuid.UUID] = None,
    active_only: bool = True,
    user: TokenData = Depends(get_current_user),
):
    """List monitored targets."""
    if project_id:
        await require_project_access(project_id, user)
    async with db_manager.get_session() as session:
        query = select(MonitoredTarget)
        if project_id:
            query = query.where(MonitoredTarget.project_id == project_id)
        if active_only:
            query = query.where(MonitoredTarget.is_active == True)
        query = query.order_by(MonitoredTarget.name)

        result = await session.execute(query)
        targets = result.scalars().all()

        return [
            MonitoredTargetResponse(
                id=str(t.id),
                project_id=str(t.project_id),
                name=t.name,
                url=t.url,
                method=t.method,
                expected_status=t.expected_status,
                timeout_seconds=t.timeout_seconds,
                interval_seconds=t.interval_seconds,
                is_active=t.is_active,
                last_check_at=t.last_check_at.isoformat() if t.last_check_at else None,
                last_status=t.last_status,
                last_latency_ms=t.last_latency_ms,
                is_degraded=t.is_degraded,
                created_at=t.created_at.isoformat(),
            )
            for t in targets
        ]


@router.get("/{target_id}")
async def get_target(
    target_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Get a single monitored target."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(MonitoredTarget).where(MonitoredTarget.id == target_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")

        return MonitoredTargetResponse(
            id=str(target.id),
            project_id=str(target.project_id),
            name=target.name,
            url=target.url,
            method=target.method,
            expected_status=target.expected_status,
            timeout_seconds=target.timeout_seconds,
            interval_seconds=target.interval_seconds,
            is_active=target.is_active,
            last_check_at=target.last_check_at.isoformat() if target.last_check_at else None,
            last_status=target.last_status,
            last_latency_ms=target.last_latency_ms,
            is_degraded=target.is_degraded,
            created_at=target.created_at.isoformat(),
        )


@router.patch("/{target_id}")
async def update_target(
    target_id: uuid.UUID,
    req: MonitoredTargetUpdate,
    user: TokenData = Depends(get_current_user),
):
    """Update a monitored target."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(MonitoredTarget).where(MonitoredTarget.id == target_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")

        if req.url is not None:
            from app.security.ssrf import ssrf_protector, SSRFError
            try:
                ssrf_protector.validate_url(req.url)
            except SSRFError as e:
                raise HTTPException(status_code=400, detail=f"URL validation failed: {e}")
            target.url = req.url

        if req.name is not None:
            target.name = req.name
        if req.method is not None:
            target.method = req.method
        if req.expected_status is not None:
            target.expected_status = req.expected_status
        if req.timeout_seconds is not None:
            target.timeout_seconds = req.timeout_seconds
        if req.interval_seconds is not None:
            target.interval_seconds = req.interval_seconds
        if req.is_active is not None:
            target.is_active = req.is_active
        if req.headers is not None:
            target.headers = req.headers

        await session.flush()

        return MonitoredTargetResponse(
            id=str(target.id),
            project_id=str(target.project_id),
            name=target.name,
            url=target.url,
            method=target.method,
            expected_status=target.expected_status,
            timeout_seconds=target.timeout_seconds,
            interval_seconds=target.interval_seconds,
            is_active=target.is_active,
            last_check_at=target.last_check_at.isoformat() if target.last_check_at else None,
            last_status=target.last_status,
            last_latency_ms=target.last_latency_ms,
            is_degraded=target.is_degraded,
            created_at=target.created_at.isoformat(),
        )


@router.delete("/{target_id}", status_code=204)
async def delete_target(
    target_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Delete a monitored target."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(MonitoredTarget).where(MonitoredTarget.id == target_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")

        await session.delete(target)
        await session.flush()
