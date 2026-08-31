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
from app.security.auth import TokenData, get_current_user

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
    created_at: str
    updated_at: str


class ProjectHealthResponse(BaseModel):
    project_id: str
    name: str
    health: str  # healthy, degraded, unhealthy, unknown
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
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat(),
            )
            for p in projects
        ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
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
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    req: ProjectUpdate,
    user: TokenData = Depends(get_current_user),
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
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )


@router.get("/{project_id}/health", response_model=ProjectHealthResponse)
async def project_health(
    project_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
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

        # Determine health
        health = "healthy"
        if active_incidents > 0:
            health = "degraded" if active_incidents < 3 else "unhealthy"
        if unhealthy_deps > 0:
            health = "degraded"

        return ProjectHealthResponse(
            project_id=str(project_id),
            name=project.name,
            health=health,
            total_events=event_count,
            active_incidents=active_incidents,
            total_deployments=deployment_count,
            healthy_dependencies=healthy_deps,
            unhealthy_dependencies=unhealthy_deps,
            recent_error_rate=0.0,  # TODO: compute from recent events
        )
