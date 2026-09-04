"""
hi.myrepo - Runbooks API

Runbook management, proposal, approval, and execution tracking.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import Runbook, RunbookExecution, RunbookExecutionStatus, RunbookStatus
from app.runbooks.engine import RunbookProposal, runbook_engine
from app.security.auth import TokenData, get_current_user, require_incident_access, get_user_project_ids

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


class RunbookExecutionResponse(BaseModel):
    id: str
    runbook_id: str
    incident_id: str
    status: str
    approved_by: str | None
    approved_at: str | None
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    created_at: str


class RunbookApprovalRequest(BaseModel):
    approved_by: str


class RunbookExecuteRequest(BaseModel):
    target_url: str | None = None


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


@router.get("/executions")
async def list_executions(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(get_current_user),
):
    """List runbook executions across the user's organization."""
    user_project_ids = await get_user_project_ids(user)
    if not user_project_ids:
        return {"executions": [], "total": 0}

    async with db_manager.get_session() as session:
        from app.database.models import Incident
        from sqlalchemy import func as sqlfunc

        # Base query: executions for incidents belonging to user's projects
        base = (
            select(RunbookExecution)
            .join(Incident, RunbookExecution.incident_id == Incident.id)
            .where(Incident.project_id.in_(user_project_ids))
        )
        if status_filter:
            base = base.where(RunbookExecution.status == status_filter)

        count_q = select(sqlfunc.count()).select_from(base.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        base = base.order_by(RunbookExecution.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(base)
        executions = result.scalars().all()

        return {
            "executions": [
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
                    "created_at": e.created_at.isoformat(),
                }
                for e in executions
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }


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


@router.post("/executions/{execution_id}/execute")
async def execute_runbook(
    execution_id: uuid.UUID,
    req: RunbookExecuteRequest,
    user: TokenData = Depends(get_current_user),
):
    """Execute an approved runbook execution."""
    from app.runbooks.executor import safe_executor

    async with db_manager.get_session() as session:
        exec_result = await session.execute(
            select(RunbookExecution).where(RunbookExecution.id == execution_id)
        )
        execution = exec_result.scalar_one_or_none()
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        await require_incident_access(execution.incident_id, user)

        if execution.status != RunbookExecutionStatus.APPROVED:
            raise HTTPException(status_code=400, detail=f"Execution is not approved (status: {execution.status})")

        # Transition to RUNNING
        execution.status = RunbookExecutionStatus.RUNNING
        execution.started_at = datetime.now(timezone.utc)
        execution.audit_trail = {
            **execution.audit_trail,
            "execution_started": {
                "started_by": user.user_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        await session.flush()

        # Execute the safe operation
        result = await safe_executor.execute(execution, session, target_url=req.target_url)

        # Complete execution
        execution.status = (
            RunbookExecutionStatus.SUCCEEDED if result.success
            else RunbookExecutionStatus.FAILED
        )
        execution.completed_at = datetime.now(timezone.utc)
        execution.execution_log = [*execution.execution_log, {
            "type": "execution_result",
            "success": result.success,
            "message": result.message,
            "details": result.details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
        if not result.success:
            execution.error_message = result.message

        # Update runbook stats
        from app.database.models import Runbook
        rb_result = await session.execute(select(Runbook).where(Runbook.id == execution.runbook_id))
        runbook = rb_result.scalar_one_or_none()
        if runbook:
            if result.success:
                runbook.historical_success_count += 1
            else:
                runbook.historical_failure_count += 1

        # Audit log for execution
        from app.database.models import AuditLog
        audit = AuditLog(
            id=uuid.uuid4(),
            action="runbook.execution.completed" if result.success else "runbook.execution.failed",
            actor_type="user",
            actor_id=user.user_id,
            resource_type="runbook_execution",
            resource_id=str(execution.id),
            incident_id=execution.incident_id,
            details={
                "success": result.success,
                "message": result.message,
            },
            outcome="success" if result.success else "failure",
        )
        session.add(audit)
        await session.flush()

        # Auto-trigger verification after successful execution
        verification_result = None
        if result.success and result.details.get("verification"):
            verification_result = result.details["verification"]
        elif result.success:
            # Run independent verification
            try:
                from app.verification.engine import VerificationPlan, verification_engine
                from app.database.models import Incident as IncModel, MonitoredTarget

                inc_result = await session.execute(select(IncModel).where(IncModel.id == execution.incident_id))
                inc = inc_result.scalar_one_or_none()
                if inc:
                    # Find the target URL from incident metadata or affected_component
                    target_url = inc.affected_component or (inc.metadata_ or {}).get("target_url")
                    checks = []
                    if target_url:
                        from app.verification.engine import VerificationCheck
                        checks.append(VerificationCheck(
                            name="health_check",
                            check_type="health_check",
                            target_url=target_url,
                            timeout_seconds=10,
                        ))
                    if checks:
                        plan = VerificationPlan(
                            incident_id=execution.incident_id,
                            execution_id=execution.id,
                            verification_type="health_check",
                            checks=checks,
                            required_passes=3,
                        )
                        verification = await verification_engine.create_verification(plan, session)
                        # Transition execution to verification state
                        execution.status = RunbookExecutionStatus.VERIFICATION_RUNNING
                        execution.execution_log = [*execution.execution_log, {
                            "type": "verification_started",
                            "verification_id": str(verification.id),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }]
                        await session.flush()

                        vr = await verification_engine.run_verification(verification.id, plan, session)
                        verification_result = {"success": vr.success, "checks_passed": vr.checks_passed}

                        # Complete execution with verification result
                        execution.status = (
                            RunbookExecutionStatus.VERIFICATION_SUCCEEDED if vr.success
                            else RunbookExecutionStatus.VERIFICATION_FAILED
                        )
                        execution.execution_log = [*execution.execution_log, {
                            "type": "verification_completed",
                            "success": vr.success,
                            "checks_passed": vr.checks_passed,
                            "checks_failed": vr.checks_failed,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }]

                        # Audit verification
                        v_audit = AuditLog(
                            id=uuid.uuid4(),
                            action="verification.completed" if vr.success else "verification.failed",
                            actor_type="system",
                            resource_type="verification",
                            resource_id=str(verification.id),
                            incident_id=execution.incident_id,
                            details={
                                "execution_id": str(execution.id),
                                "success": vr.success,
                                "checks_passed": vr.checks_passed,
                                "checks_failed": vr.checks_failed,
                            },
                            outcome="success" if vr.success else "failure",
                        )
                        session.add(v_audit)
                        await session.flush()
            except Exception as e:
                import structlog
                structlog.get_logger().warning("auto_verification_failed", error=str(e))

        return {
            "execution_id": str(execution.id),
            "status": execution.status,
            "success": result.success,
            "message": result.message,
            "details": result.details,
            "verification": verification_result,
        }


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
