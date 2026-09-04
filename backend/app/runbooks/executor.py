"""
hi.myrepo - Safe Runbook Executor

CRITICAL SAFETY RULES:
1. Only explicitly registered operations may execute
2. AI cannot invent arbitrary shell commands
3. Every execution is idempotent
4. Every execution produces an audit trail
5. Unknown runbook codes are rejected with an error

Each runbook declares:
- code: unique identifier (e.g., RB-01)
- executor: the function that performs the action
- verification: how to verify success
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AuditLog,
    Event,
    Incident,
    RunbookExecution,
    RunbookExecutionStatus,
    VerificationRun,
    VerificationStatus,
)

logger = structlog.get_logger()


class ExecutionResult:
    """Result of a safe runbook execution."""
    def __init__(self, success: bool, message: str, details: dict = None):
        self.success = success
        self.message = message
        self.details = details or {}
        self.started_at = datetime.now(timezone.utc)
        self.completed_at = datetime.now(timezone.utc)


# ============================================================================
# PREDEFINED SAFE EXECUTORS
# ============================================================================
# These are the ONLY operations that may execute through the runbook system.
# Each executor is a bounded, reversible, auditable operation.
# ============================================================================

async def execute_health_check(target_url: str, timeout: int = 10) -> ExecutionResult:
    """RB-01: Verify endpoint health via HTTP GET."""
    try:
        async with httpx.AsyncClient() as client:
            start = time.time()
            response = await client.get(target_url, timeout=timeout)
            latency_ms = (time.time() - start) * 1000
            success = 200 <= response.status_code < 400
            return ExecutionResult(
                success=success,
                message=f"Health check {'passed' if success else 'failed'}: HTTP {response.status_code} in {latency_ms:.0f}ms",
                details={
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                    "target_url": target_url,
                },
            )
    except Exception as e:
        return ExecutionResult(
            success=False,
            message=f"Health check failed: {e}",
            details={"error": str(e), "target_url": target_url},
        )


async def execute_error_rate_check(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    session: AsyncSession,
    threshold: float = 5.0,
) -> ExecutionResult:
    """RB-01 verify: Check that error rate has dropped below threshold."""
    from sqlalchemy import func

    # Get incident
    inc_result = await session.execute(select(Incident).where(Incident.id == incident_id))
    incident = inc_result.scalar_one_or_none()
    if not incident:
        return ExecutionResult(success=False, message="Incident not found")

    # Count errors since incident detection
    error_count = (await session.execute(
        select(func.count()).where(
            Event.project_id == project_id,
            Event.event_type == "ERROR_DETECTED",
            Event.received_at >= incident.detected_at,
        )
    )).scalar() or 0

    # Count recent successes (last 5 minutes)
    five_min_ago = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    from datetime import timedelta
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    success_count = (await session.execute(
        select(func.count()).where(
            Event.project_id == project_id,
            Event.event_type == "HEARTBEAT_SUCCESS",
            Event.received_at >= five_min_ago,
        )
    )).scalar() or 0

    success = error_count <= threshold and success_count > 0
    return ExecutionResult(
        success=success,
        message=f"Error rate check: {error_count} errors (threshold: {threshold}), {success_count} recent successes",
        details={
            "error_count": error_count,
            "threshold": threshold,
            "recent_successes": success_count,
            "incident_id": str(incident_id),
        },
    )


# Registry of safe operations
# Each entry maps a runbook code to its executor function and parameters
SAFE_EXECUTORS = {
    "RB-01": {
        "name": "Service Restart Health Check",
        "executor": execute_health_check,
        "params": ["target_url"],
        "verification": execute_error_rate_check,
        "description": "Verify service health and error rate after restart",
    },
    "RB-02": {
        "name": "Cache Clear Verification",
        "executor": execute_health_check,
        "params": ["target_url"],
        "verification": execute_error_rate_check,
        "description": "Verify service health after cache clear",
    },
    "RB-03": {
        "name": "Dependency Failover Verification",
        "executor": execute_health_check,
        "params": ["target_url"],
        "verification": execute_error_rate_check,
        "description": "Verify service health after dependency failover",
    },
    "RB-04": {
        "name": "Deployment Rollback Verification",
        "executor": execute_health_check,
        "params": ["target_url"],
        "verification": execute_error_rate_check,
        "description": "Verify service health after deployment rollback",
    },
    "RB-05": {
        "name": "Queue Drain Verification",
        "executor": execute_health_check,
        "params": ["target_url"],
        "verification": execute_error_rate_check,
        "description": "Verify service health after queue drain",
    },
}


class SafeRunbookExecutor:
    """
    Executes only predefined, registered runbook operations.
    Never executes arbitrary commands from AI or user input.
    """

    async def execute(
        self,
        execution: RunbookExecution,
        session: AsyncSession,
        target_url: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute a runbook. Only succeeds if the runbook code is in the registry.
        """
        # Get the runbook to find its code
        from app.database.models import Runbook
        runbook_result = await session.execute(
            select(Runbook).where(Runbook.id == execution.runbook_id)
        )
        runbook = runbook_result.scalar_one_or_none()
        if not runbook:
            return ExecutionResult(success=False, message="Runbook not found")

        # Check registry — only pre-approved codes may execute
        executor_info = SAFE_EXECUTORS.get(runbook.code)
        if not executor_info:
            return ExecutionResult(
                success=False,
                message=f"Runbook '{runbook.code}' has no registered executor. Cannot execute unknown operations.",
            )

        # Get incident for context
        inc_result = await session.execute(
            select(Incident).where(Incident.id == execution.incident_id)
        )
        incident = inc_result.scalar_one_or_none()
        if not incident:
            return ExecutionResult(success=False, message="Incident not found")

        # Determine target URL from incident if not provided
        if not target_url:
            target_url = incident.affected_component or incident.metadata_.get("target_url")

        # Execute the safe operation
        executor_fn = executor_info["executor"]
        if executor_fn == execute_health_check:
            result = await executor_fn(target_url=target_url)
        else:
            result = ExecutionResult(success=False, message=f"Unknown executor type: {executor_fn}")

        # Run verification if available
        if result.success and executor_info.get("verification"):
            verifier = executor_info["verification"]
            if verifier == execute_error_rate_check:
                verify_result = await verifier(
                    project_id=incident.project_id,
                    incident_id=incident.id,
                    session=session,
                )
                result.details["verification"] = {
                    "success": verify_result.success,
                    "message": verify_result.message,
                    "details": verify_result.details,
                }
                # Verification failure means overall failure
                if not verify_result.success:
                    result = ExecutionResult(
                        success=False,
                        message=f"Execution succeeded but verification failed: {verify_result.message}",
                        details={**result.details, "verification_failed": True},
                    )

        result.completed_at = datetime.now(timezone.utc)
        return result


# Global safe executor singleton
safe_executor = SafeRunbookExecutor()
