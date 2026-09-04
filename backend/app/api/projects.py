"""
hi.myrepo - Projects API

Project management and health monitoring.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import db_manager
from app.database.models import (
    Deployment,
    Dependency,
    Environment,
    ErrorGroup,
    Event,
    Incident,
    MonitoredTarget,
    Project,
)
from app.security.auth import TokenData, get_current_user, require_project_access

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    repository_url: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    repository_url: str | None = None
    is_active: bool | None = None
    autonomy_level: int | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    repository_url: str | None
    organization_id: str
    is_active: bool
    autonomy_level: int
    monitoring_status: str
    monitoring_started_at: str | None
    monitoring_stopped_at: str | None
    created_at: str
    updated_at: str


class ProjectHealthResponse(BaseModel):
    project_id: str
    name: str
    health: str  # healthy, degraded, unhealthy, unknown, no_targets, stopped
    monitoring_status: str
    total_targets: int
    active_targets: int
    total_events: int
    active_incidents: int
    total_deployments: int
    healthy_dependencies: int
    unhealthy_dependencies: int
    recent_error_rate: float


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    req: ProjectCreate,
    user: TokenData = Depends(get_current_user),
):
    """Create a new project."""
    async with db_manager.get_session() as session:
        # Check slug uniqueness within org
        existing = await session.execute(
            select(Project).where(
                Project.organization_id == uuid.UUID(user.organization_id),
                Project.slug == req.slug,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Project slug already exists")

        project = Project(
            id=uuid.uuid4(),
            name=req.name,
            slug=req.slug,
            description=req.description,
            repository_url=req.repository_url,
            organization_id=uuid.UUID(user.organization_id),
        )
        session.add(project)
        await session.flush()

        # Create default production environment
        env = Environment(
            id=uuid.uuid4(),
            name="production",
            project_id=project.id,
        )
        session.add(env)
        await session.flush()

        return ProjectResponse(
            id=str(project.id),
            name=project.name,
            slug=project.slug,
            description=project.description,
            repository_url=project.repository_url,
            organization_id=str(project.organization_id),
            is_active=project.is_active,
            autonomy_level=project.autonomy_level,
            monitoring_status=project.monitoring_status,
            monitoring_started_at=project.monitoring_started_at.isoformat() if project.monitoring_started_at else None,
            monitoring_stopped_at=project.monitoring_stopped_at.isoformat() if project.monitoring_stopped_at else None,
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user: TokenData = Depends(get_current_user),
):
    """List all projects for the user's organization."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project)
            .where(Project.organization_id == uuid.UUID(user.organization_id))
            .order_by(Project.created_at.desc())
        )
        projects = result.scalars().all()

        return [
            ProjectResponse(
                id=str(p.id),
                name=p.name,
                slug=p.slug,
                description=p.description,
                repository_url=p.repository_url,
                organization_id=str(p.organization_id),
                is_active=p.is_active,
                autonomy_level=p.autonomy_level,
                monitoring_status=p.monitoring_status,
                monitoring_started_at=p.monitoring_started_at.isoformat() if p.monitoring_started_at else None,
                monitoring_stopped_at=p.monitoring_stopped_at.isoformat() if p.monitoring_stopped_at else None,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat(),
            )
            for p in projects
        ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: TokenData = Depends(require_project_access),
):
    """Get a single project."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        return ProjectResponse(
            id=str(project.id),
            name=project.name,
            slug=project.slug,
            description=project.description,
            repository_url=project.repository_url,
            organization_id=str(project.organization_id),
            is_active=project.is_active,
            autonomy_level=project.autonomy_level,
            monitoring_status=project.monitoring_status,
            monitoring_started_at=project.monitoring_started_at.isoformat() if project.monitoring_started_at else None,
            monitoring_stopped_at=project.monitoring_stopped_at.isoformat() if project.monitoring_stopped_at else None,
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    req: ProjectUpdate,
    user: TokenData = Depends(require_project_access),
):
    """Update a project."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if req.name is not None:
            project.name = req.name
        if req.description is not None:
            project.description = req.description
        if req.repository_url is not None:
            project.repository_url = req.repository_url
        if req.is_active is not None:
            project.is_active = req.is_active
        if req.autonomy_level is not None:
            project.autonomy_level = req.autonomy_level

        project.updated_at = datetime.now(timezone.utc)
        await session.flush()

        return ProjectResponse(
            id=str(project.id),
            name=project.name,
            slug=project.slug,
            description=project.description,
            repository_url=project.repository_url,
            organization_id=str(project.organization_id),
            is_active=project.is_active,
            autonomy_level=project.autonomy_level,
            monitoring_status=project.monitoring_status,
            monitoring_started_at=project.monitoring_started_at.isoformat() if project.monitoring_started_at else None,
            monitoring_stopped_at=project.monitoring_stopped_at.isoformat() if project.monitoring_stopped_at else None,
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )


@router.post("/{project_id}/monitoring/start")
async def start_monitoring(
    project_id: uuid.UUID,
    user: TokenData = Depends(require_project_access),
):
    """Start monitoring a project. Idempotent."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        now = datetime.now(timezone.utc)

        # Idempotent: if already active, return current state
        if project.monitoring_status == "active":
            return {
                "status": "active",
                "message": "Monitoring already active",
                "started_at": project.monitoring_started_at.isoformat() if project.monitoring_started_at else None,
            }

        project.monitoring_status = "active"
        project.monitoring_started_at = now
        project.monitoring_stopped_at = None
        project.updated_at = now

        # Audit log
        from app.database.models import AuditLog
        audit = AuditLog(
            id=uuid.uuid4(),
            action="monitoring.started",
            actor_type="user",
            actor_id=user.user_id,
            resource_type="project",
            resource_id=str(project.id),
            project_id=project.id,
            details={"monitoring_status": "active"},
            outcome="success",
        )
        session.add(audit)

        await session.flush()

        return {
            "status": "active",
            "message": "Monitoring started",
            "started_at": now.isoformat(),
        }


@router.post("/{project_id}/monitoring/stop")
async def stop_monitoring(
    project_id: uuid.UUID,
    user: TokenData = Depends(require_project_access),
):
    """Stop monitoring a project. Idempotent. Preserves all historical data."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        now = datetime.now(timezone.utc)

        # Idempotent: if already stopped, return current state
        if project.monitoring_status == "stopped":
            return {
                "status": "stopped",
                "message": "Monitoring already stopped",
                "stopped_at": project.monitoring_stopped_at.isoformat() if project.monitoring_stopped_at else None,
            }

        project.monitoring_status = "stopped"
        project.monitoring_stopped_at = now
        project.updated_at = now

        # Audit log
        from app.database.models import AuditLog
        audit = AuditLog(
            id=uuid.uuid4(),
            action="monitoring.stopped",
            actor_type="user",
            actor_id=user.user_id,
            resource_type="project",
            resource_id=str(project.id),
            project_id=project.id,
            details={"monitoring_status": "stopped"},
            outcome="success",
        )
        session.add(audit)

        await session.flush()

        return {
            "status": "stopped",
            "message": "Monitoring stopped. Historical data preserved.",
            "stopped_at": now.isoformat(),
        }


@router.get("/{project_id}/health", response_model=ProjectHealthResponse)
async def project_health(
    project_id: uuid.UUID,
    user: TokenData = Depends(require_project_access),
):
    """Get project health summary."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Count events
        event_count = (await session.execute(
            select(func.count()).where(Event.project_id == project_id)
        )).scalar() or 0

        # Active incidents
        active_incidents = (await session.execute(
            select(func.count()).where(
                Incident.project_id == project_id,
                Incident.status.notin_(["RESOLVED", "ESCALATED"]),
            )
        )).scalar() or 0

        # Deployments
        deployment_count = (await session.execute(
            select(func.count()).where(Deployment.project_id == project_id)
        )).scalar() or 0

        # Dependencies
        dep_result = await session.execute(
            select(func.count()).where(
                Dependency.project_id == project_id,
                Dependency.is_healthy == True,
            )
        )
        healthy_deps = dep_result.scalar() or 0

        dep_result2 = await session.execute(
            select(func.count()).where(
                Dependency.project_id == project_id,
                Dependency.is_healthy == False,
            )
        )
        unhealthy_deps = dep_result2.scalar() or 0

        # Compute recent error rate from the last hour of events
        from datetime import timedelta
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        total_recent = (await session.execute(
            select(func.count()).where(
                Event.project_id == project_id,
                Event.received_at >= one_hour_ago,
            )
        )).scalar() or 0

        error_recent = (await session.execute(
            select(func.count()).where(
                Event.project_id == project_id,
                Event.event_type == "ERROR_DETECTED",
                Event.received_at >= one_hour_ago,
            )
        )).scalar() or 0

        recent_error_rate = round(error_recent / total_recent, 4) if total_recent > 0 else 0.0

        # Count monitored targets
        total_targets = (await session.execute(
            select(func.count()).where(MonitoredTarget.project_id == project_id)
        )).scalar() or 0
        active_targets = (await session.execute(
            select(func.count()).where(
                MonitoredTarget.project_id == project_id,
                MonitoredTarget.is_active == True,
            )
        )).scalar() or 0

        # Determine health — semantics-aware
        health = "healthy"
        if project.monitoring_status != "active":
            health = "stopped"
        elif total_targets == 0:
            health = "no_targets"
        elif active_incidents > 0:
            health = "degraded" if active_incidents < 3 else "unhealthy"
        elif unhealthy_deps > 0:
            health = "degraded"
        elif recent_error_rate > 0.1:
            health = "degraded"
        elif recent_error_rate > 0.3:
            health = "unhealthy"

        return ProjectHealthResponse(
            project_id=str(project_id),
            name=project.name,
            health=health,
            monitoring_status=project.monitoring_status,
            total_targets=total_targets,
            active_targets=active_targets,
            total_events=event_count,
            active_incidents=active_incidents,
            total_deployments=deployment_count,
            healthy_dependencies=healthy_deps,
            unhealthy_dependencies=unhealthy_deps,
            recent_error_rate=recent_error_rate,
        )
