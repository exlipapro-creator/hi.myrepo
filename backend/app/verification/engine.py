"""
hi.myrepo - Verification Engine

Every automated remediation must have verification.
A failed verification should not be interpreted as success.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    Incident,
    VerificationRun,
    VerificationStatus,
)


class VerificationCheck(BaseModel):
    """A single verification check."""
    name: str
    check_type: str  # health_check, error_rate, response_time, custom
    target_url: Optional[str] = None
    expected_value: Optional[str] = None
    threshold: Optional[float] = None
    timeout_seconds: int = 10


class VerificationPlan(BaseModel):
    """A complete verification plan for a remediation."""
    incident_id: uuid.UUID
    execution_id: Optional[uuid.UUID] = None
    verification_type: str = "health_check"  # health_check, error_rate, custom
    checks: list[VerificationCheck] = []
    required_passes: int = 3  # consecutive passes required
    wait_seconds: int = 30  # wait before starting checks
    max_duration_seconds: int = 300  # max time for verification


class VerificationResult(BaseModel):
    """Result of a verification run."""
    success: bool
    checks_performed: list[dict]
    checks_passed: int
    checks_failed: int
    error_message: Optional[str] = None


class VerificationEngine:
    """
    Post-remediation verification.
    ROLLBACK → wait → health check → 3 consecutive successful requests
    → observe error stream → compare error rate → RESOLVED
    """

    async def create_verification(
        self,
        plan: VerificationPlan,
        session: AsyncSession,
    ) -> VerificationRun:
        """Create a verification run."""
        verification = VerificationRun(
            id=uuid.uuid4(),
            incident_id=plan.incident_id,
            execution_id=plan.execution_id,
            status=VerificationStatus.PENDING,
            verification_type=plan.verification_type,
            checks_performed=[],
            started_at=datetime.now(timezone.utc),
        )
        session.add(verification)
        await session.flush()
        return verification

    async def run_verification(
        self,
        verification_id: uuid.UUID,
        plan: VerificationPlan,
        session: AsyncSession,
    ) -> VerificationResult:
        """Execute verification checks."""
        result = await session.execute(
            select(VerificationRun).where(VerificationRun.id == verification_id)
        )
        verification = result.scalar_one_or_none()
        if not verification:
            raise ValueError(f"Verification {verification_id} not found")

        verification.status = VerificationStatus.RUNNING
        verification.started_at = datetime.now(timezone.utc)
        await session.flush()

        checks_performed = []
        checks_passed = 0
        checks_failed = 0
        consecutive_passes = 0

        for check in plan.checks:
            check_result = await self._execute_check(check, session=session, incident_id=plan.incident_id)
            checks_performed.append(check_result)

            if check_result["success"]:
                checks_passed += 1
                consecutive_passes += 1
            else:
                checks_failed += 1
                consecutive_passes = 0

            # If we have enough consecutive passes, we can stop early
            if consecutive_passes >= plan.required_passes:
                break

        # Determine overall success
        success = consecutive_passes >= plan.required_passes

        # Update verification record
        verification.status = (
            VerificationStatus.SUCCEEDED if success
            else VerificationStatus.FAILED
        )
        verification.checks_performed = checks_performed
        verification.checks_passed = checks_passed
        verification.checks_failed = checks_failed
        verification.success = success
        verification.completed_at = datetime.now(timezone.utc)

        if not success:
            verification.error_message = (
                f"Verification failed: {checks_failed} check(s) failed, "
                f"only {consecutive_passes} consecutive pass(es) "
                f"(required: {plan.required_passes})"
            )

        await session.flush()

        return VerificationResult(
            success=success,
            checks_performed=checks_performed,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            error_message=verification.error_message,
        )

    async def _execute_check(
        self,
        check: VerificationCheck,
        session: Optional[AsyncSession] = None,
        incident_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """Execute a single verification check."""
        import httpx

        result = {
            "name": check.name,
            "type": check.check_type,
            "success": False,
            "details": {},
        }

        try:
            if check.check_type == "health_check" and check.target_url:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        check.target_url,
                        timeout=check.timeout_seconds,
                    )
                    result["details"] = {
                        "status_code": response.status_code,
                        "latency_ms": response.elapsed.total_seconds() * 1000,
                    }
                    result["success"] = 200 <= response.status_code < 300

            elif check.check_type == "error_rate" and session and incident_id:
                # Query the event store for ERROR_DETECTED events since incident creation
                from sqlalchemy import func
                from app.database.models import Incident

                inc_result = await session.execute(
                    select(Incident).where(Incident.id == incident_id)
                )
                incident = inc_result.scalar_one_or_none()

                if incident:
                    # Count errors for this project since incident was detected
                    error_count = (await session.execute(
                        select(func.count()).where(
                            Event.project_id == incident.project_id,
                            Event.event_type == "ERROR_DETECTED",
                            Event.received_at >= incident.detected_at,
                        )
                    )).scalar() or 0

                    threshold = check.threshold or 5.0  # default: max 5 errors allowed
                    result["details"] = {
                        "error_count": error_count,
                        "threshold": threshold,
                        "incident_id": str(incident_id),
                    }
                    result["success"] = error_count <= threshold
                else:
                    result["details"]["note"] = "Incident not found — cannot check error rate"
                    result["success"] = False

            elif check.check_type == "error_rate":
                # No session/incident — cannot perform error rate check
                result["details"]["note"] = "Error rate check requires incident context"
                result["success"] = False

            elif check.check_type == "response_time":
                if check.target_url:
                    async with httpx.AsyncClient() as client:
                        import time
                        start = time.time()
                        response = await client.get(
                            check.target_url,
                            timeout=check.timeout_seconds,
                        )
                        latency_ms = (time.time() - start) * 1000
                        result["details"] = {
                            "latency_ms": latency_ms,
                            "threshold": check.threshold,
                        }
                        if check.threshold:
                            result["success"] = latency_ms <= check.threshold
                        else:
                            result["success"] = response.status_code < 400

        except Exception as e:
            result["details"]["error"] = str(e)
            result["success"] = False

        return result

    async def get_verification_history(
        self,
        incident_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[VerificationRun]:
        """Get all verification runs for an incident."""
        result = await session.execute(
            select(VerificationRun)
            .where(VerificationRun.incident_id == incident_id)
            .order_by(VerificationRun.created_at)
        )
        return list(result.scalars().all())


# Global verification engine singleton
verification_engine = VerificationEngine()
