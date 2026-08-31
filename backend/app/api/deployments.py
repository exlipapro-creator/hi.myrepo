"""
hi.myrepo - Deployments API

Record deployment events for correlation with incidents.
External services (GitHub, Vercel, Render) can push deployment events.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.database.connection import db_manager
from app.database.models import Deployment, Project
from app.events.spine import EventEnvelope
from app.pipeline.orchestrator import pipeline
from app.security.auth import TokenData, get_current_user

router = APIRouter()


class DeploymentCreate(BaseModel):
    project_id: uuid.UUID
    environment: str = "production"
    status: str  # started, succeeded, failed, rolled_back
    commit_sha: Optional[str] = None
    commit_message: Optional[str] = None
    branch: Optional[str] = None
    version: Optional[str] = None
    deployed_by: Optional[str] = None
    source: str = "api"  # github, vercel, manual, api
    deployment_url: Optional[str] = None


class DeploymentResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    status: str
    commit_sha: Optional[str]
    commit_message: Optional[str]
    branch: Optional[str]
    version: Optional[str]
    source: str
    created_at: str


@router.post("", status_code=201)
async def record_deployment(
    req: DeploymentCreate,
    user: TokenData = Depends(get_current_user),
):
    """Record a deployment event."""
    async with db_manager.get_session() as session:
        # Verify project
        result = await session.execute(
            select(Project).where(Project.id == req.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Create deployment record
        deployment = Deployment(
            id=uuid.uuid4(),
            project_id=req.project_id,
            environment=req.environment,
            status=req.status,
            commit_sha=req.commit_sha,
            commit_message=req.commit_message,
            branch=req.branch,
            version=req.version,
            deployed_by=req.deployed_by,
            source=req.source,
            deployment_url=req.deployment_url,
            started_at=datetime.now(timezone.utc) if req.status == "started" else None,
            completed_at=datetime.now(timezone.utc) if req.status in ("succeeded", "failed") else None,
        )
        session.add(deployment)
        await session.flush()

        # Map status to event type
        status_event_map = {
            "started": "DEPLOYMENT_STARTED",
            "succeeded": "DEPLOYMENT_SUCCEEDED",
            "failed": "DEPLOYMENT_FAILED",
            "rolled_back": "DEPLOYMENT_ROLLED_BACK",
        }
        event_type = status_event_map.get(req.status, "DEPLOYMENT_STARTED")
        severity = "high" if req.status in ("failed",) else "low"

        # Emit event through pipeline for regression correlation
        envelope = EventEnvelope(
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            source=req.source,
            source_type="system",
            project_id=req.project_id,
            severity=severity,
            idempotency_key=f"deployment:{deployment.id}",
            payload={
                "deployment_id": str(deployment.id),
                "commit_sha": req.commit_sha,
                "commit_message": req.commit_message,
                "branch": req.branch,
                "version": req.version,
                "environment": req.environment,
                "deployed_by": req.deployed_by,
            },
            metadata={
                "source": "deployment_api",
            },
        )

        result = await pipeline.process_deployment_event(
            envelope,
            deployment_data={"commit_sha": req.commit_sha},
            session=session,
        )

        return {
            "id": str(deployment.id),
            "status": deployment.status,
            "event_type": event_type,
            "event_id": str(result.event.id) if result.event else None,
            "regression_check": result.actions_taken,
        }


@router.get("")
async def list_deployments(
    project_id: Optional[uuid.UUID] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(get_current_user),
):
    """List deployments."""
    async with db_manager.get_session() as session:
        query = select(Deployment)
        if project_id:
            query = query.where(Deployment.project_id == project_id)
        query = query.order_by(Deployment.created_at.desc()).limit(limit).offset(offset)

        result = await session.execute(query)
        deployments = result.scalars().all()

        return [
            DeploymentResponse(
                id=str(d.id),
                project_id=str(d.project_id),
                environment=d.environment,
                status=d.status,
                commit_sha=d.commit_sha,
                commit_message=d.commit_message,
                branch=d.branch,
                version=d.version,
                source=d.source,
                created_at=d.created_at.isoformat(),
            )
            for d in deployments
        ]


@router.get("/{deployment_id}")
async def get_deployment(
    deployment_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Get a single deployment."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        deployment = result.scalar_one_or_none()
        if not deployment:
            raise HTTPException(status_code=404, detail="Deployment not found")

        return DeploymentResponse(
            id=str(deployment.id),
            project_id=str(deployment.project_id),
            environment=deployment.environment,
            status=deployment.status,
            commit_sha=deployment.commit_sha,
            commit_message=deployment.commit_message,
            branch=deployment.branch,
            version=deployment.version,
            source=deployment.source,
            created_at=deployment.created_at.isoformat(),
        )
