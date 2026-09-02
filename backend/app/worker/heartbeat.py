"""
hi.myrepo - Heartbeat Worker

In-process heartbeat worker that checks monitored targets on their configured intervals.

Architecture:
- Runs as an asyncio background task within the FastAPI process
- Only processes targets belonging to projects with monitoring_status="active"
- Respects each target's interval_seconds configuration
- Emits HEARTBEAT_SUCCESS/HEARTBEAT_FAILURE events through the event spine
- Respects SSRF protections
- Bounded concurrency (max 5 concurrent checks)
- Logs all activity for observability

Limitations (single-instance):
- Worker state is lost on process restart
- No distributed scheduling (single-process only)
- For multi-instance: use Redis-based task queue

Production safety:
- Never checks targets for stopped projects
- Respects target timeout configuration
- Handles network errors gracefully
- Emits events through existing pipeline (no parallel storage)
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from sqlalchemy import select

from app.database.connection import db_manager
from app.database.models import HeartbeatResult, MonitoredTarget, Project
from app.events.spine import EventEnvelope
from app.pipeline.orchestrator import pipeline
from app.security.ssrf import ssrf_protector, SSRFError

logger = structlog.get_logger()

# Worker configuration
_CHECK_INTERVAL_SECONDS = 30  # How often to scan for targets due for checking
_MAX_CONCURRENT_CHECKS = 5    # Max simultaneous heartbeat requests
_HEALTH_CHECK_TIMEOUT = 10    # Max seconds per individual health check


class HeartbeatWorker:
    """In-process heartbeat worker for monitoring active project targets."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check_times: dict[str, float] = {}  # target_id -> last_check_timestamp
        self._active_checks = 0

    async def start(self):
        """Start the heartbeat worker background task."""
        if self._running:
            logger.warning("heartbeat_worker_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("heartbeat_worker_started", interval=_CHECK_INTERVAL_SECONDS)

    async def stop(self):
        """Stop the heartbeat worker gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("heartbeat_worker_stopped")

    async def _run_loop(self):
        """Main worker loop — scans for targets due for checking."""
        while self._running:
            try:
                await self._check_due_targets()
            except Exception as e:
                logger.error("heartbeat_worker_error", error=str(e))
            await asyncio.sleep(_CHECK_INTERVAL_SECONDS)

    async def _check_due_targets(self):
        """Find and check all targets that are due for a heartbeat."""
        try:
            async with db_manager.get_session() as session:
                # Find active projects with monitoring enabled
                result = await session.execute(
                    select(Project).where(Project.monitoring_status == "active")
                )
                active_projects = result.scalars().all()

                if not active_projects:
                    return

                active_project_ids = [p.id for p in active_projects]

                # Find active targets for these projects
                target_result = await session.execute(
                    select(MonitoredTarget).where(
                        MonitoredTarget.project_id.in_(active_project_ids),
                        MonitoredTarget.is_active == True,
                    )
                )
                targets = target_result.scalars().all()

                now = time.time()
                due_targets = []

                for target in targets:
                    target_key = str(target.id)
                    last_check = self._last_check_times.get(target_key, 0)
                    interval = target.interval_seconds or 60

                    if now - last_check >= interval:
                        due_targets.append(target)

                if not due_targets:
                    return

                logger.info(
                    "heartbeat_check_batch",
                    targets_due=len(due_targets),
                    active_projects=len(active_projects),
                )

                # Check targets with bounded concurrency
                semaphore = asyncio.Semaphore(_MAX_CONCURRENT_CHECKS)
                tasks = [
                    self._check_target_with_semaphore(target, semaphore)
                    for target in due_targets
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error("heartbeat_scan_error", error=str(e))

    async def _check_target_with_semaphore(self, target: MonitoredTarget, semaphore: asyncio.Semaphore):
        """Check a target with concurrency limiting."""
        async with semaphore:
            await self._check_single_target(target)

    async def _check_single_target(self, target: MonitoredTarget):
        """Execute a single heartbeat check against a target."""
        target_key = str(target.id)
        self._last_check_times[target_key] = time.time()

        # Validate URL against SSRF
        try:
            ssrf_protector.validate_url(target.url)
        except SSRFError as e:
            logger.warning("heartbeat_ssrf_blocked", target_id=target_key, url=target.url, error=str(e))
            await self._record_failure(target, 0, str(e))
            return

        try:
            start_time = time.time()
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=target.method,
                    url=target.url,
                    timeout=target.timeout_seconds or _HEALTH_CHECK_TIMEOUT,
                    headers=target.headers or {},
                )
                latency_ms = (time.time() - start_time) * 1000

                is_healthy = response.status_code == (target.expected_status or 200)
                is_degraded = not is_healthy and 200 <= response.status_code < 500

                # Record heartbeat result
                await self._record_result(
                    target=target,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    is_healthy=is_healthy,
                    is_degraded=is_degraded,
                    error_message=None if is_healthy else f"Expected {target.expected_status}, got {response.status_code}",
                )

                # Emit event through pipeline
                event_type = "HEARTBEAT_SUCCESS" if is_healthy else (
                    "HEARTBEAT_DEGRADED" if is_degraded else "HEARTBEAT_FAILURE"
                )
                severity = "low" if is_healthy else ("medium" if is_degraded else "high")

                envelope = EventEnvelope(
                    event_type=event_type,
                    occurred_at=datetime.now(timezone.utc),
                    source=target.name,
                    source_type="heartbeat",
                    project_id=target.project_id,
                    severity=severity,
                    idempotency_key=f"heartbeat:{target.id}:{int(time.time())}",
                    payload={
                        "target_id": str(target.id),
                        "target_url": target.url,
                        "status_code": response.status_code,
                        "expected_status": target.expected_status,
                        "latency_ms": round(latency_ms, 2),
                        "is_degraded": is_degraded,
                    },
                    metadata={
                        "source": "heartbeat_worker",
                        "target_name": target.name,
                    },
                )

                async with db_manager.get_session() as session:
                    await pipeline.process_heartbeat_result(envelope, session)

                logger.info(
                    "heartbeat_checked",
                    target_id=target_key,
                    target_name=target.name,
                    status_code=response.status_code,
                    latency_ms=round(latency_ms, 2),
                    healthy=is_healthy,
                )

        except httpx.TimeoutException:
            latency_ms = (target.timeout_seconds or _HEALTH_CHECK_TIMEOUT) * 1000
            await self._record_failure(target, None, "Timeout")
            await self._emit_failure_event(target, "Timeout", latency_ms)

        except httpx.RequestError as e:
            latency_ms = 0
            await self._record_failure(target, None, str(e)[:200])
            await self._emit_failure_event(target, str(e)[:200], latency_ms)

        except Exception as e:
            logger.error("heartbeat_unexpected_error", target_id=target_key, error=str(e))
            await self._record_failure(target, None, str(e)[:200])

    async def _record_result(
        self,
        target: MonitoredTarget,
        status_code: Optional[int],
        latency_ms: float,
        is_healthy: bool,
        is_degraded: bool,
        error_message: Optional[str],
    ):
        """Record a heartbeat result in the database."""
        try:
            async with db_manager.get_session() as session:
                # Update target's last check state
                target.last_check_at = datetime.now(timezone.utc)
                target.last_status = status_code
                target.last_latency_ms = latency_ms
                target.is_degraded = is_degraded
                await session.flush()

                # Create heartbeat result record
                result = HeartbeatResult(
                    id=uuid.uuid4(),
                    target_id=target.id,
                    status_code=status_code,
                    latency_ms=latency_ms,
                    is_healthy=is_healthy,
                    is_degraded=is_degraded,
                    error_message=error_message,
                )
                session.add(result)
                await session.flush()
        except Exception as e:
            logger.error("heartbeat_record_error", target_id=str(target.id), error=str(e))

    async def _record_failure(self, target: MonitoredTarget, status_code: Optional[int], error_message: str):
        """Record a failed heartbeat check."""
        await self._record_result(
            target=target,
            status_code=status_code,
            latency_ms=0,
            is_healthy=False,
            is_degraded=False,
            error_message=error_message,
        )

    async def _emit_failure_event(self, target: MonitoredTarget, error_message: str, latency_ms: float):
        """Emit a heartbeat failure event through the pipeline."""
        try:
            envelope = EventEnvelope(
                event_type="HEARTBEAT_FAILURE",
                occurred_at=datetime.now(timezone.utc),
                source=target.name,
                source_type="heartbeat",
                project_id=target.project_id,
                severity="high",
                idempotency_key=f"heartbeat:{target.id}:{int(time.time())}",
                payload={
                    "target_id": str(target.id),
                    "target_url": target.url,
                    "error": error_message,
                    "latency_ms": round(latency_ms, 2),
                },
                metadata={"source": "heartbeat_worker"},
            )

            async with db_manager.get_session() as session:
                await pipeline.process_heartbeat_result(envelope, session)
        except Exception as e:
            logger.error("heartbeat_event_error", target_id=str(target.id), error=str(e))


# Global heartbeat worker singleton
heartbeat_worker = HeartbeatWorker()
