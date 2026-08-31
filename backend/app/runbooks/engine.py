"""
hi.myrepo - Runbook Engine

Runbooks are explicitly defined operational procedures.
AI can recommend runbooks. AI cannot invent arbitrary shell commands and
execute them against production.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AuditLog,
    Incident,
    Runbook,
    RunbookExecution,
    RunbookExecutionStatus,
    RunbookStatus,
)


class RunbookProposal(BaseModel):
    """A proposed runbook action."""
    runbook_id: uuid.UUID
    incident_id: uuid.UUID
    confidence: float
    reasoning: str
    expected_outcome: str
    risks: list[str] = []
    blast_radius: str = "low"


class RunbookEngine:
    """
    Manages runbook lifecycle and execution.
    Runbooks must be explicitly defined — no arbitrary command execution.
    """

    async def propose_runbook(
        self,
        proposal: RunbookProposal,
        session: AsyncSession,
    ) -> RunbookExecution:
        """
        Create a runbook execution proposal.
        This does NOT execute the runbook — it creates a pending execution
        that requires approval.
        """
        # Verify runbook exists and is active
        result = await session.execute(
            select(Runbook).where(Runbook.id == proposal.runbook_id)
        )
        runbook = result.scalar_one_or_none()
        if not runbook:
            raise ValueError(f"Runbook {proposal.runbook_id} not found")
        if runbook.status != RunbookStatus.ACTIVE:
            raise ValueError(f"Runbook '{runbook.code}' is not active (status: {runbook.status})")

        # Create pending execution
        execution = RunbookExecution(
            id=uuid.uuid4(),
            runbook_id=proposal.runbook_id,
            incident_id=proposal.incident_id,
            status=RunbookExecutionStatus.PENDING,
            audit_trail={
                "proposal": {
                    "confidence": proposal.confidence,
                    "reasoning": proposal.reasoning,
                    "expected_outcome": proposal.expected_outcome,
                    "risks": proposal.risks,
                    "blast_radius": proposal.blast_radius,
                    "proposed_at": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
        session.add(execution)

        # Create audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            action="runbook_proposed",
            actor_type="system",
            resource_type="runbook_execution",
            resource_id=str(execution.id),
            incident_id=proposal.incident_id,
            details={
                "runbook_code": runbook.code,
                "runbook_name": runbook.name,
                "confidence": proposal.confidence,
            },
            evidence={
                "reasoning": proposal.reasoning,
                "risks": proposal.risks,
            },
            authorization={"status": "pending_approval"},
            outcome="proposed",
        )
        session.add(audit)

        await session.flush()
        return execution

    async def approve_execution(
        self,
        execution_id: uuid.UUID,
        approved_by: str,
        session: AsyncSession,
    ) -> RunbookExecution:
        """Approve a pending runbook execution."""
        result = await session.execute(
            select(RunbookExecution).where(RunbookExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        if execution.status != RunbookExecutionStatus.PENDING:
            raise ValueError(f"Execution is not pending (status: {execution.status})")

        execution.status = RunbookExecutionStatus.APPROVED
        execution.approved_by = approved_by
        execution.approved_at = datetime.now(timezone.utc)
        execution.audit_trail = {
            **execution.audit_trail,
            "approval": {
                "approved_by": approved_by,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # Audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            action="runbook_approved",
            actor_type="user",
            actor_id=approved_by,
            resource_type="runbook_execution",
            resource_id=str(execution.id),
            incident_id=execution.incident_id,
            details={"execution_id": str(execution.id)},
            authorization={"approved_by": approved_by},
            outcome="success",
        )
        session.add(audit)

        await session.flush()
        return execution

    async def start_execution(
        self,
        execution_id: uuid.UUID,
        session: AsyncSession,
    ) -> RunbookExecution:
        """Start an approved runbook execution."""
        result = await session.execute(
            select(RunbookExecution).where(RunbookExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        if execution.status != RunbookExecutionStatus.APPROVED:
            raise ValueError(f"Execution is not approved (status: {execution.status})")

        execution.status = RunbookExecutionStatus.RUNNING
        execution.started_at = datetime.now(timezone.utc)
        await session.flush()
        return execution

    async def complete_execution(
        self,
        execution_id: uuid.UUID,
        success: bool,
        session: AsyncSession,
        log_entries: Optional[list[dict]] = None,
        error_message: Optional[str] = None,
    ) -> RunbookExecution:
        """Mark a runbook execution as complete or failed."""
        result = await session.execute(
            select(RunbookExecution).where(RunbookExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        execution.status = (
            RunbookExecutionStatus.SUCCEEDED if success
            else RunbookExecutionStatus.FAILED
        )
        execution.completed_at = datetime.now(timezone.utc)
        execution.error_message = error_message
        if log_entries:
            execution.execution_log = [*execution.execution_log, *log_entries]

        # Update runbook statistics
        runbook_result = await session.execute(
            select(Runbook).where(Runbook.id == execution.runbook_id)
        )
        runbook = runbook_result.scalar_one_or_none()
        if runbook:
            if success:
                runbook.historical_success_count += 1
            else:
                runbook.historical_failure_count += 1

        await session.flush()
        return execution

    async def get_active_runbooks(
        self, session: AsyncSession
    ) -> list[Runbook]:
        """Retrieve all active runbooks."""
        result = await session.execute(
            select(Runbook)
            .where(Runbook.status == RunbookStatus.ACTIVE)
            .order_by(Runbook.code)
        )
        return list(result.scalars().all())

    async def get_execution_history(
        self,
        incident_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[RunbookExecution]:
        """Get all runbook executions for an incident."""
        result = await session.execute(
            select(RunbookExecution)
            .where(RunbookExecution.incident_id == incident_id)
            .order_by(RunbookExecution.created_at)
        )
        return list(result.scalars().all())


# Global runbook engine singleton
runbook_engine = RunbookEngine()
