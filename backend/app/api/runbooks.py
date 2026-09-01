"""
hi.myrepo - Runbooks API

Runbook management, proposal, approval, and execution tracking.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import Runbook, RunbookExecution, RunbookStatus
from app.runbooks.engine import RunbookProposal, runbook_engine
from app.security.auth import TokenData, get_current_user, require_incident_access

router = APIRouter()


class RunbookResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    status: str
    is_reversible: bool
    required_autonomy_level: int
    max_blast_radius: str
    historical_success_count: int
    historical_failure_count: int


class RunbookApprovalRequest(BaseModel):
    approved_by: str


@router.get("", response_model=list[RunbookResponse])
async def list_runbooks(
    user: TokenData = Depends(get_current_user),
):
    """List all runbooks."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Runbook).order_by(Runbook.code)
        )
        runbooks = result.scalars().all()

        return [
            RunbookResponse(
                id=str(r.id),
                code=r.code,
                name=r.name,
                description=r.description,
                status=r.status,
                is_reversible=r.is_reversible,
                required_autonomy_level=r.required_autonomy_level,
                max_blast_radius=r.max_blast_radius,
                historical_success_count=r.historical_success_count,
                historical_failure_count=r.historical_failure_count,
            )
            for r in runbooks
        ]


@router.get("/{runbook_id}", response_model=RunbookResponse)
async def get_runbook(
    runbook_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Get a single runbook."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Runbook).where(Runbook.id == runbook_id)
        )
        runbook = result.scalar_one_or_none()
        if not runbook:
            raise HTTPException(status_code=404, detail="Runbook not found")

        return RunbookResponse(
            id=str(runbook.id),
            code=runbook.code,
            name=runbook.name,
            description=runbook.description,
            status=runbook.status,
            is_reversible=runbook.is_reversible,
            required_autonomy_level=runbook.required_autonomy_level,
            max_blast_radius=runbook.max_blast_radius,
            historical_success_count=runbook.historical_success_count,
            historical_failure_count=runbook.historical_failure_count,
        )


@router.post("/propose")
async def propose_runbook(
    proposal: RunbookProposal,
    user: TokenData = Depends(get_current_user),
):
    """Propose a runbook execution (creates pending execution)."""
    # Verify user's org owns the target incident
    await require_incident_access(proposal.incident_id, user)
    async with db_manager.get_session() as session:
        try:
            execution = await runbook_engine.propose_runbook(proposal, session)
            return {
                "execution_id": str(execution.id),
                "status": execution.status,
                "message": "Runbook execution proposed — awaiting approval",
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/{execution_id}/approve")
async def approve_execution(
    execution_id: uuid.UUID,
    req: RunbookApprovalRequest,
    user: TokenData = Depends(get_current_user),
):
    """Approve a pending runbook execution."""
    # First verify the execution exists and user has access to its incident
    async with db_manager.get_session() as session:
        exec_result = await session.execute(
            select(RunbookExecution).where(RunbookExecution.id == execution_id)
        )
        execution = exec_result.scalar_one_or_none()
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        # Verify user's org owns the incident this execution targets
        await require_incident_access(execution.incident_id, user)

        try:
            execution = await runbook_engine.approve_execution(
                execution_id=execution_id,
                approved_by=req.approved_by,
                session=session,
            )
            return {
                "execution_id": str(execution.id),
                "status": execution.status,
                "message": "Execution approved",
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.get("/executions/{incident_id}")
async def get_execution_history(
    incident_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """Get runbook execution history for an incident."""
    # Verify user's org owns this incident
    await require_incident_access(incident_id, user)
    async with db_manager.get_session() as session:
        executions = await runbook_engine.get_execution_history(incident_id, session)
        return [
            {
                "id": str(e.id),
                "runbook_id": str(e.runbook_id),
                "incident_id": str(e.incident_id),
                "status": e.status,
                "approved_by": e.approved_by,
                "approved_at": e.approved_at.isoformat() if e.approved_at else None,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "error_message": e.error_message,
                "rollback_performed": e.rollback_performed,
                "created_at": e.created_at.isoformat(),
            }
            for e in executions
        ]
