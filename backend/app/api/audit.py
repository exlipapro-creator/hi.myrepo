"""
hi.myrepo - Audit Logs API

Every consequential action must be recorded.
WHO? WHAT? WHEN? WHY? BASED ON WHAT EVIDENCE? AUTHORIZED BY WHOM?
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.database.connection import db_manager
from app.database.models import AuditLog
from app.security.auth import TokenData, get_current_user, require_project_access, get_user_project_ids

router = APIRouter()


@router.get("")
async def list_audit_logs(
    action: Optional[str] = None,
    actor_type: Optional[str] = None,
    resource_type: Optional[str] = None,
    project_id: Optional[uuid.UUID] = None,
    incident_id: Optional[uuid.UUID] = None,
    outcome: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    exclude_pipeline: bool = Query(default=False, description="Exclude pipeline_processed noise"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(get_current_user),
):
    """Query audit logs with filtering and server-side pagination."""
    from datetime import datetime as dt

    if project_id:
        await require_project_access(project_id, user)
    else:
        user_project_ids = await get_user_project_ids(user)
        if not user_project_ids:
            return {"logs": [], "total": 0, "limit": limit, "offset": offset, "has_more": False}
    async with db_manager.get_session() as session:
        query = select(AuditLog)

        if action:
            query = query.where(AuditLog.action == action)
        elif exclude_pipeline:
            query = query.where(AuditLog.action.notlike("pipeline_%"))
        if actor_type:
            query = query.where(AuditLog.actor_type == actor_type)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if outcome:
            query = query.where(AuditLog.outcome == outcome)
        if project_id:
            query = query.where(AuditLog.project_id == project_id)
        else:
            # Scope to user's org projects
            query = query.where(AuditLog.project_id.in_(user_project_ids))
        if incident_id:
            query = query.where(AuditLog.incident_id == incident_id)
        if from_date:
            try:
                from_dt = dt.fromisoformat(from_date.replace("Z", "+00:00"))
                query = query.where(AuditLog.created_at >= from_dt)
            except ValueError:
                pass
        if to_date:
            try:
                to_dt = dt.fromisoformat(to_date.replace("Z", "+00:00"))
                query = query.where(AuditLog.created_at <= to_dt)
            except ValueError:
                pass

        # Count
        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        logs = result.scalars().all()

        return {
            "logs": [
                {
                    "id": str(l.id),
                    "action": l.action,
                    "actor_type": l.actor_type,
                    "actor_id": l.actor_id,
                    "resource_type": l.resource_type,
                    "resource_id": l.resource_id,
                    "project_id": str(l.project_id) if l.project_id else None,
                    "incident_id": str(l.incident_id) if l.incident_id else None,
                    "details": l.details,
                    "evidence": l.evidence,
                    "authorization": l.authorization,
                    "outcome": l.outcome,
                    "ip_address": l.ip_address,
                    "created_at": l.created_at.isoformat(),
                }
                for l in logs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }
