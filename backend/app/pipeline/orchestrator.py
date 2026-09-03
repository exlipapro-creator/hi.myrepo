"""
hi.myrepo - Event Pipeline Orchestrator

The pipeline connects isolated engines into the production event flow:

    Event Ingestion
        ↓
    Fingerprinting
        ↓
    Error Group Deduplication
        ↓
    Incident Creation (if warranted)
        ↓
    Adaptive Investigation Level Selection
        ↓
    Engineering Council (AI or deterministic)
        ↓
    Policy Evaluation
        ↓
    Runbook Proposal
        ↓
    Verification (post-remediation)
        ↓
    Memory Recording

Every step is deterministic except Council investigation (which is probabilistic).
Policy always remains the authority layer.

Design principles:
- Deterministic core, probabilistic intelligence
- Safety before autonomy
- Evidence-driven decisions
- Audit everything
- Fail closed for dangerous operations
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import db_manager
from app.database.models import (
    AuditLog,
    Deployment,
    ErrorGroup,
    Event,
    Incident,
    IncidentAnalysis,
    IncidentStatus,
    MemoryRecord,
    Policy,
    Project,
    Runbook,
    RunbookExecution,
    VerificationRun,
)
from app.events.fingerprinting import ErrorInput, FingerprintResult, fingerprint_engine
from app.events.spine import EventEnvelope, EventProcessor, event_processor
from app.incidents.engine import IncidentCreate, incident_engine
from app.council.engine import CouncilEngine, CouncilVerdict, council_engine
from app.policy.engine import PolicyContext, PolicyDecision, PolicyEvaluation, policy_engine
from app.runbooks.engine import RunbookProposal, runbook_engine
from app.verification.engine import VerificationPlan, verification_engine
from app.memory.engine import MemoryCreate, memory_engine

logger = structlog.get_logger()


class InvestigationLevel(int, Enum):
    """Adaptive investigation levels — depth proportional to severity."""
    OBSERVE = 0           # Single transient event — record only
    CORRELATE = 1         # Repeated failure — fingerprint and group
    LIGHTWEIGHT_AI = 2    # Correlated anomaly — single AI investigation
    FULL_COUNCIL = 3      # Probable incident — Engineering Council
    EMERGENCY = 4         # High-severity — full council + human escalation


class PipelineResult:
    """Result of running an event through the pipeline."""

    def __init__(self):
        self.event: Optional[Event] = None
        self.fingerprint: Optional[FingerprintResult] = None
        self.error_group: Optional[ErrorGroup] = None
        self.incident: Optional[Incident] = None
        self.investigation_level: InvestigationLevel = InvestigationLevel.OBSERVE
        self.council_verdict: Optional[CouncilVerdict] = None
        self.policy_evaluation: Optional[PolicyEvaluation] = None
        self.runbook_execution: Optional[RunbookExecution] = None
        self.verification_run: Optional[VerificationRun] = None
        self.memory_record: Optional[MemoryRecord] = None
        self.actions_taken: list[str] = []
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "event_id": str(self.event.id) if self.event else None,
            "fingerprint": self.fingerprint.fingerprint if self.fingerprint else None,
            "incident_id": str(self.incident.id) if self.incident else None,
            "investigation_level": self.investigation_level.value,
            "council_confidence": self.council_verdict.confidence if self.council_verdict else None,
            "policy_decision": self.policy_evaluation.decision.value if self.policy_evaluation else None,
            "actions_taken": self.actions_taken,
            "errors": self.errors,
        }


class PipelineOrchestrator:
    """
    The central pipeline that connects all engines.

    This is NOT an AI agent. It is a deterministic orchestration layer
    that routes events through the appropriate processing stages.
    """

    # Thresholds for adaptive investigation
    ERROR_GROUP_THRESHOLD_FOR_INCIDENT = 3      # 3+ errors with same fingerprint → incident
    SEVERITY_FOR_COUNCIL = "high"                # high/critical → full council
    SEVERITY_FOR_LIGHTWEIGHT_AI = "medium"       # medium → lightweight investigation

    async def process_event(
        self,
        envelope: EventEnvelope,
        session: AsyncSession,
    ) -> PipelineResult:
        """
        Process a single event through the complete pipeline.
        Returns a PipelineResult describing what happened at each stage.
        """
        result = PipelineResult()

        # ── Stage 1: Persist the event ────────────────────────────────
        try:
            event = await event_processor.process_event(envelope, session)
            result.event = event
            result.actions_taken.append("event_persisted")
            logger.info(
                "pipeline_event_persisted",
                event_id=str(event.id),
                event_type=event.event_type,
            )
        except Exception as e:
            result.errors.append(f"event_persistence_failed: {e}")
            logger.error("pipeline_event_persistence_failed", error=str(e))
            return result

        # ── Stage 2: Fingerprint if error event ───────────────────────
        if envelope.event_type in ("ERROR_DETECTED",):
            await self._process_error_fingerprint(event, envelope, session, result)

        # ── Stage 3: Determine investigation level ────────────────────
        result.investigation_level = self._determine_investigation_level(event, result)
        logger.info(
            "pipeline_investigation_level",
            level=result.investigation_level.value,
            event_type=event.event_type,
        )

        # ── Stage 4: Adaptive investigation ───────────────────────────
        if result.investigation_level.value >= InvestigationLevel.FULL_COUNCIL.value:
            await self._run_council_investigation(event, session, result)
        elif result.investigation_level.value >= InvestigationLevel.LIGHTWEIGHT_AI.value:
            await self._run_lightweight_investigation(event, session, result)

        # ── Stage 5: Policy evaluation (if incident exists) ──────────
        if result.incident and result.council_verdict:
            await self._evaluate_policy(event, result.incident, result.council_verdict, session, result)

        # ── Stage 6: Record memory (if resolved or significant) ──────
        if result.incident and result.incident.status in (IncidentStatus.RESOLVED, IncidentStatus.ESCALATED):
            await self._record_memory(result.incident, result, session)

        # ── Audit the entire pipeline run ─────────────────────────────
        await self._audit_pipeline_run(event, result, session)

        return result

    async def process_deployment_event(
        self,
        envelope: EventEnvelope,
        deployment_data: dict,
        session: AsyncSession,
    ) -> PipelineResult:
        """
        Process a deployment event and check for regression correlation.
        """
        result = await self.process_event(envelope, session)

        # If this is a deployment succeeded, check for recent errors
        if envelope.event_type == "DEPLOYMENT_SUCCEEDED":
            await self._check_deployment_regression(envelope, deployment_data, session, result)

        return result

    async def process_heartbeat_result(
        self,
        envelope: EventEnvelope,
        session: AsyncSession,
    ) -> PipelineResult:
        """Process a heartbeat result event."""
        result = await self.process_event(envelope, session)

        # If heartbeat failed, check for incident-worthy patterns
        if envelope.event_type in ("HEARTBEAT_FAILURE", "HEARTBEAT_DEGRADED"):
            await self._check_heartbeat_pattern(envelope, session, result)

        # If heartbeat recovered, check for open incidents to update
        if envelope.event_type == "HEARTBEAT_SUCCESS":
            await self._check_heartbeat_recovery(envelope, session, result)

        return result

    # ── Internal pipeline stages ──────────────────────────────────────

    async def _process_error_fingerprint(
        self,
        event: Event,
        envelope: EventEnvelope,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Fingerprint the error and create/update error group."""
        payload = envelope.payload or {}

        error_input = ErrorInput(
            error_type=payload.get("error_type", "UnknownError"),
            error_message=payload.get("error_message", payload.get("message", "")),
            stack_trace=payload.get("stack_trace"),
            file_location=payload.get("file_location"),
            route=payload.get("route"),
            release=payload.get("release"),
        )

        fingerprint_result = fingerprint_engine.fingerprint(error_input)
        result.fingerprint = fingerprint_result
        result.actions_taken.append("error_fingerprinted")

        # Find or create error group
        from sqlalchemy import select
        existing = await session.execute(
            select(ErrorGroup).where(
                ErrorGroup.fingerprint == fingerprint_result.fingerprint,
                ErrorGroup.project_id == event.project_id,
            )
        )
        error_group = existing.scalar_one_or_none()

        if error_group:
            # Update existing error group
            error_group.occurrence_count += 1
            error_group.last_seen = datetime.now(timezone.utc)
            result.error_group = error_group
            result.actions_taken.append("error_group_updated")

            # Check if we should create an incident
            if error_group.occurrence_count >= self.ERROR_GROUP_THRESHOLD_FOR_INCIDENT:
                if not error_group.incident_id:
                    await self._create_incident_from_error_group(
                        error_group, event, fingerprint_result, session, result
                    )
        else:
            # Create new error group
            error_group = ErrorGroup(
                id=uuid.uuid4(),
                fingerprint=fingerprint_result.fingerprint,
                project_id=event.project_id,
                error_type=fingerprint_result.error_type,
                error_message=fingerprint_result.normalized_message,
                normalized_stack=fingerprint_result.normalized_stack,
                route=fingerprint_result.route,
                file_location=fingerprint_result.file_location,
                occurrence_count=1,
            )
            session.add(error_group)
            await session.flush()
            result.error_group = error_group
            result.actions_taken.append("error_group_created")

    async def _create_incident_from_error_group(
        self,
        error_group: ErrorGroup,
        event: Event,
        fingerprint_result: FingerprintResult,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Create an incident from a persistent error group."""
        # Determine severity based on occurrence count and event severity
        severity = self._calculate_severity(error_group.occurrence_count, event.severity)

        incident_data = IncidentCreate(
            project_id=event.project_id,
            severity=severity,
            title=f"{fingerprint_result.error_type}: {fingerprint_result.normalized_message[:200]}",
            summary=f"Error fingerprint {fingerprint_result.fingerprint} observed {error_group.occurrence_count} times",
            affected_service=event.source,
            affected_component=fingerprint_result.route,
            fingerprint=fingerprint_result.fingerprint,
            correlation_id=event.correlation_id,
        )

        incident = await incident_engine.create_incident(incident_data, session)

        # Link error group to incident
        error_group.incident_id = incident.id
        result.incident = incident
        result.actions_taken.append("incident_created")

        logger.warning(
            "pipeline_incident_created",
            incident_id=str(incident.id),
            severity=severity,
            fingerprint=fingerprint_result.fingerprint,
            occurrences=error_group.occurrence_count,
        )

    def _determine_investigation_level(
        self, event: Event, result: PipelineResult
    ) -> InvestigationLevel:
        """Determine the appropriate investigation depth."""
        severity = (event.severity or "low").lower()

        # Event type determines minimum level
        if event.event_type.startswith("HEARTBEAT_"):
            if event.event_type == "HEARTBEAT_SUCCESS":
                return InvestigationLevel.OBSERVE
            return InvestigationLevel.CORRELATE

        if event.event_type == "ERROR_DETECTED":
            if result.error_group and result.error_group.occurrence_count > self.ERROR_GROUP_THRESHOLD_FOR_INCIDENT:
                if severity in ("high", "critical"):
                    return InvestigationLevel.FULL_COUNCIL
                elif severity == "medium":
                    return InvestigationLevel.LIGHTWEIGHT_AI
            return InvestigationLevel.CORRELATE

        if event.event_type.startswith("DEPLOYMENT_"):
            if event.event_type == "DEPLOYMENT_FAILED":
                return InvestigationLevel.LIGHTWEIGHT_AI
            return InvestigationLevel.OBSERVE

        if event.event_type.startswith("AI_PROVIDER_"):
            if event.event_type == "AI_PROVIDER_FAILED":
                return InvestigationLevel.CORRELATE
            return InvestigationLevel.OBSERVE

        if event.event_type.startswith("INCIDENT_"):
            return InvestigationLevel.FULL_COUNCIL

        return InvestigationLevel.OBSERVE

    def _calculate_severity(self, occurrence_count: int, event_severity: Optional[str]) -> str:
        """Calculate incident severity from occurrence count and event severity."""
        base = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        base_level = base.get((event_severity or "low").lower(), 0)

        # Escalate based on occurrences
        if occurrence_count >= 50:
            base_level = max(base_level, 3)  # critical
        elif occurrence_count >= 20:
            base_level = max(base_level, 2)  # high
        elif occurrence_count >= 5:
            base_level = max(base_level, 1)  # medium

        levels = ["low", "medium", "high", "critical"]
        return levels[min(base_level, len(levels) - 1)]

    async def _run_council_investigation(
        self,
        event: Event,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Run the full Engineering Council investigation."""
        incident = result.incident
        if not incident:
            return

        # Build investigation context
        context = await self._build_investigation_context(incident, session)

        # Run the council
        verdict = await council_engine.investigate(incident, context)
        result.council_verdict = verdict
        result.actions_taken.append("council_investigation_complete")

        # Persist the council analysis
        analysis = IncidentAnalysis(
            id=uuid.uuid4(),
            incident_id=incident.id,
            analysis_type="council",
            root_cause=verdict.root_cause,
            confidence=verdict.confidence,
            evidence=verdict.evidence,
            alternative_hypotheses=verdict.alternative_hypotheses,
            blast_radius_assessment=verdict.blast_radius,
            recommended_action=verdict.recommended_action,
            risk_assessment=verdict.risk_assessment,
            required_verification=verdict.required_verification,
            council_rounds_used=verdict.council_rounds_used,
            council_budget_exceeded=verdict.budget_exceeded,
        )
        session.add(analysis)

        # Update incident with council findings
        incident.confidence = verdict.confidence
        incident.root_cause = verdict.root_cause
        incident.blast_radius = verdict.blast_radius

        # Transition incident to DIAGNOSED
        try:
            await incident_engine.transition(
                incident.id, IncidentStatus.DIAGNOSED, session,
                details={"council_verdict": verdict.model_dump(mode="json")},
            )
            result.actions_taken.append("incident_diagnosed")
        except ValueError:
            # May already be in DIAGNOSED or later state
            pass

    async def _run_lightweight_investigation(
        self,
        event: Event,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Run a lightweight single-agent investigation."""
        # For medium severity — just record the analysis as a single-agent investigation
        incident = result.incident
        if not incident:
            return

        context = await self._build_investigation_context(incident, session)
        verdict = await council_engine.investigate(incident, context)
        result.council_verdict = verdict
        result.actions_taken.append("lightweight_investigation_complete")

        analysis = IncidentAnalysis(
            id=uuid.uuid4(),
            incident_id=incident.id,
            analysis_type="single_ai",
            root_cause=verdict.root_cause,
            confidence=verdict.confidence,
            evidence=verdict.evidence,
            alternative_hypotheses=verdict.alternative_hypotheses,
            recommended_action=verdict.recommended_action,
            council_rounds_used=verdict.council_rounds_used,
        )
        session.add(analysis)

    async def _build_investigation_context(
        self, incident: Incident, session: AsyncSession
    ) -> dict:
        """Build the investigation context for the council."""
        from sqlalchemy import select, func

        context = {
            "incident": {
                "id": str(incident.id),
                "severity": incident.severity,
                "status": incident.status,
                "fingerprint": incident.fingerprint,
                "affected_service": incident.affected_service,
                "affected_component": incident.affected_component,
            },
            "error_groups": [],
            "recent_deployment": None,
            "dependencies": [],
            "heartbeat_results": [],
            "similar_incidents": [],
            "memory_records": [],
        }

        # Get recent error groups for this project
        if incident.fingerprint:
            eg_result = await session.execute(
                select(ErrorGroup).where(
                    ErrorGroup.fingerprint == incident.fingerprint,
                    ErrorGroup.project_id == incident.project_id,
                )
            )
            error_groups = eg_result.scalars().all()
            context["error_groups"] = [
                {
                    "error_type": eg.error_type,
                    "error_message": eg.error_message,
                    "occurrence_count": eg.occurrence_count,
                    "route": eg.route,
                }
                for eg in error_groups
            ]

        # Get recent deployment
        deploy_result = await session.execute(
            select(Deployment).where(
                Deployment.project_id == incident.project_id,
            ).order_by(Deployment.created_at.desc()).limit(1)
        )
        deployment = deploy_result.scalar_one_or_none()
        if deployment:
            context["recent_deployment"] = {
                "commit_sha": deployment.commit_sha,
                "status": deployment.status,
                "branch": deployment.branch,
                "timestamp": deployment.created_at.isoformat() if deployment.created_at else None,
            }

        # Get similar historical incidents
        if incident.fingerprint:
            similar = await incident_engine.find_similar_incidents(
                incident.fingerprint, incident.project_id, session, limit=5
            )
            context["similar_incidents"] = [
                {
                    "id": str(s.id),
                    "status": s.status,
                    "severity": s.severity,
                    "resolved_at": s.resolved_at.isoformat() if s.resolved_at else None,
                }
                for s in similar if str(s.id) != str(incident.id)
            ]

        return context

    async def _evaluate_policy(
        self,
        event: Event,
        incident: Incident,
        verdict: CouncilVerdict,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Evaluate policy to determine if any action is permitted."""
        from app.database.models import RunbookStatus

        # Find the recommended runbook (if any)
        recommended_runbook = None
        if verdict.recommended_action:
            rb_result = await session.execute(
                select(Runbook).where(
                    Runbook.status == RunbookStatus.ACTIVE,
                ).order_by(Runbook.code)
            )
            runbooks = rb_result.scalars().all()
            # Simple heuristic: match by keywords in recommended_action
            for rb in runbooks:
                action_lower = verdict.recommended_action.lower()
                rb_lower = (rb.name + " " + rb.description).lower()
                if any(word in rb_lower for word in action_lower.split() if len(word) > 4):
                    recommended_runbook = rb
                    break

        # Read the project's actual autonomy level
        project_result = await session.execute(
            select(Project).where(Project.id == incident.project_id)
        )
        project = project_result.scalar_one_or_none()
        project_autonomy = project.autonomy_level if project else 0

        context = PolicyContext(
            incident_id=incident.id,
            incident={
                "severity": incident.severity,
                "confidence": verdict.confidence,
                "blast_radius": verdict.blast_radius,
            },
            runbook={
                "is_reversible": recommended_runbook.is_reversible if recommended_runbook else True,
                "max_blast_radius": recommended_runbook.max_blast_radius if recommended_runbook else "low",
                "required_autonomy_level": recommended_runbook.required_autonomy_level if recommended_runbook else 3,
            } if recommended_runbook else None,
            verification_available=True,
            autonomy_level=project_autonomy,
        )

        evaluation = await policy_engine.evaluate(context, "runbook", session)
        result.policy_evaluation = evaluation
        result.actions_taken.append(f"policy_evaluated:{evaluation.decision.value}")

        # Store recommended runbook on incident
        if recommended_runbook:
            incident.recommended_runbook_id = recommended_runbook.id

    async def _record_memory(
        self,
        incident: Incident,
        result: PipelineResult,
        session: AsyncSession,
    ):
        """Record the incident outcome in memory."""
        memory = MemoryCreate(
            project_id=incident.project_id,
            incident_id=incident.id,
            fingerprint=incident.fingerprint,
            category="resolution" if incident.status == IncidentStatus.RESOLVED else "incident",
            title=incident.title or f"Incident {str(incident.id)[:8]}",
            summary=incident.summary or "No summary",
            root_cause=incident.root_cause,
            resolution=f"Status: {incident.status}" if incident.status == IncidentStatus.RESOLVED else None,
            runbook_code=None,
            confidence_at_resolution=incident.confidence,
            was_autonomous=False,
            success=incident.status == IncidentStatus.RESOLVED,
            tags=[incident.severity, incident.status],
        )

        record = await memory_engine.record_outcome(memory, session)
        result.memory_record = record
        result.actions_taken.append("memory_recorded")

    async def _check_deployment_regression(
        self,
        envelope: EventEnvelope,
        deployment_data: dict,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Check if a deployment is correlated with recent errors."""
        from sqlalchemy import select, func

        project_id = envelope.project_id
        deploy_time = envelope.occurred_at

        # Count errors since deployment
        error_count_result = await session.execute(
            select(func.count()).where(
                Event.project_id == project_id,
                Event.event_type == "ERROR_DETECTED",
                Event.received_at >= deploy_time,
            )
        )
        error_count = error_count_result.scalar() or 0

        if error_count > 0:
            result.actions_taken.append(f"deployment_regression_check:{error_count}_errors_since_deploy")
            logger.warning(
                "pipeline_deployment_regression_possible",
                project_id=str(project_id),
                errors_since_deploy=error_count,
                commit_sha=deployment_data.get("commit_sha"),
            )

    async def _check_heartbeat_pattern(
        self,
        envelope: EventEnvelope,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Check if heartbeat failures form a pattern worth investigating.

        When 3+ heartbeat failures occur within the current hour for the same project,
        create an incident if one doesn't already exist for this fingerprint.
        """
        from sqlalchemy import select, func

        project_id = envelope.project_id
        payload = envelope.payload or {}
        target_id = payload.get("target_id", "unknown")
        target_url = payload.get("target_url", "unknown")

        # Count recent heartbeat failures for this specific target
        # (prevents different targets' failures from collapsing into one count)
        failure_count_result = await session.execute(
            select(func.count()).where(
                Event.project_id == project_id,
                Event.event_type.in_(["HEARTBEAT_FAILURE", "HEARTBEAT_DEGRADED"]),
                Event.received_at >= datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
                Event.payload["target_id"].astext == target_id,
            )
        )
        failure_count = failure_count_result.scalar() or 0

        if failure_count >= 3:
            result.actions_taken.append(f"heartbeat_pattern_detected:{failure_count}_failures")
            logger.warning(
                "pipeline_heartbeat_pattern",
                project_id=str(project_id),
                failures_this_hour=failure_count,
                target_id=target_id,
            )

            # Generate a deterministic fingerprint for this heartbeat target
            # Include failure class to distinguish different failure modes:
            # HTTP 500 vs 503 vs DNS vs TLS vs timeout
            import hashlib
            failure_class = payload.get("failure_class", "unknown")
            status_code = payload.get("status_code", 0)
            fingerprint_input = f"heartbeat:{project_id}:{target_id}:{failure_class}:{status_code}"
            fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]

            # Check if an open incident already exists for this fingerprint
            existing_incident = await session.execute(
                select(Incident).where(
                    Incident.project_id == project_id,
                    Incident.fingerprint == fingerprint,
                    Incident.status.notin_([IncidentStatus.RESOLVED, IncidentStatus.REMEDIATION_FAILED]),
                )
            )
            existing = existing_incident.scalar_one_or_none()

            if existing:
                # Reset recovery verification if failure reappears
                if existing.recovery_success_count and existing.recovery_success_count > 0:
                    existing.recovery_success_count = 0
                    existing.recovery_verification_started_at = None
                    existing.metadata_ = {
                        **existing.metadata_,
                        "recovery_reset_by_failure": {
                            "timestamp": envelope.occurred_at.isoformat(),
                            "previous_count": existing.recovery_success_count,
                        },
                    }
                    result.actions_taken.append("recovery_verification_reset")
                    logger.warning(
                        "pipeline_recovery_reset_by_failure",
                        incident_id=str(existing.id),
                        target_url=target_url,
                    )

                # Update existing incident with new failure evidence
                existing.summary = (
                    f"Heartbeat failure pattern: {failure_count} failures this hour. "
                    f"Target: {target_url}"
                )
                existing.updated_at = datetime.now(timezone.utc)
                result.incident = existing
                result.actions_taken.append("heartbeat_incident_updated")
                logger.warning(
                    "pipeline_heartbeat_incident_updated",
                    incident_id=str(existing.id),
                    failures_this_hour=failure_count,
                )
            else:
                # Create a new incident from heartbeat failure pattern
                severity = "high" if failure_count >= 5 else "medium"
                incident_data = IncidentCreate(
                    project_id=project_id,
                    severity=severity,
                    title=f"Heartbeat failure: {target_url}",
                    summary=f"Heartbeat failure pattern: {failure_count} failures this hour. Target: {target_url}",
                    affected_service=envelope.source,
                    affected_component=target_url,
                    fingerprint=fingerprint,
                    correlation_id=envelope.correlation_id,
                )
                incident = await incident_engine.create_incident(incident_data, session)
                # Store target_id in metadata for recovery matching
                incident.metadata_ = {
                    **incident.metadata_,
                    "target_id": target_id,
                    "target_url": target_url,
                }
                await session.flush()
                result.incident = incident
                result.actions_taken.append("heartbeat_incident_created")
                logger.warning(
                    "pipeline_heartbeat_incident_created",
                    incident_id=str(incident.id),
                    severity=severity,
                    fingerprint=fingerprint,
                    failures_this_hour=failure_count,
                )

    async def _check_heartbeat_recovery(
        self,
        envelope: EventEnvelope,
        session: AsyncSession,
        result: PipelineResult,
    ):
        """Check if a successful heartbeat resolves an open heartbeat incident.

        When HEARTBEAT_SUCCESS arrives for a project with an open heartbeat incident,
        mark the incident as recovered (transition to TRIAGING for human verification).
        Historical failure evidence remains immutable.
        """
        from sqlalchemy import select, func

        project_id = envelope.project_id
        payload = envelope.payload or {}
        target_id = payload.get("target_id", "unknown")
        target_url = payload.get("target_url", "unknown")

        # Generate the same deterministic fingerprint used during incident creation
        # Note: recovery uses a broad fingerprint to match any failure class for this target
        import hashlib
        fingerprint_input = f"heartbeat:{project_id}:{target_id}"
        fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]
        # Also check all failure-class-specific fingerprints by querying open incidents
        # for this project+target prefix

        # Find open heartbeat incidents for this target.
        # Match by target_id stored in metadata during incident creation.
        # This correctly matches even when the target URL changes (e.g., 500 -> 200).
        from sqlalchemy import text
        existing_incident = await session.execute(
            select(Incident).where(
                Incident.project_id == project_id,
                Incident.metadata_["target_id"].astext == target_id,
                Incident.status.notin_([IncidentStatus.RESOLVED, IncidentStatus.REMEDIATION_FAILED, IncidentStatus.ESCALATED]),
            )
        )
        incident = existing_incident.scalar_one_or_none()

        if incident:
            # Record recovery metadata (immutable)
            incident.metadata_ = {
                **incident.metadata_,
                "last_recovery": {
                    "target_id": target_id,
                    "target_url": target_url,
                    "timestamp": envelope.occurred_at.isoformat(),
                },
            }
            incident.updated_at = datetime.now(timezone.utc)

            # Recovery verification window: require 3 consecutive successes
            # before transitioning to TRIAGING (prevents flapping)
            RECOVERY_VERIFICATION_THRESHOLD = 3
            incident.recovery_success_count = (incident.recovery_success_count or 0) + 1

            if incident.recovery_verification_started_at is None:
                incident.recovery_verification_started_at = datetime.now(timezone.utc)

            if incident.recovery_success_count >= RECOVERY_VERIFICATION_THRESHOLD:
                # Stable recovery confirmed - transition to TRIAGING
                try:
                    await incident_engine.transition(
                        incident.id, IncidentStatus.TRIAGING, session,
                        details={
                            "recovery_event_id": str(result.event.id) if result.event else None,
                            "recovery_verification": {
                                "successes_required": RECOVERY_VERIFICATION_THRESHOLD,
                                "successes_observed": incident.recovery_success_count,
                                "verification_started_at": incident.recovery_verification_started_at.isoformat() if incident.recovery_verification_started_at else None,
                            },
                        },
                    )
                    result.incident = incident
                    result.actions_taken.append("heartbeat_incident_recovery")
                    logger.info(
                        "pipeline_heartbeat_incident_recovery",
                        incident_id=str(incident.id),
                        target_url=target_url,
                        successes=incident.recovery_success_count,
                    )
                except ValueError:
                    result.incident = incident
                    result.actions_taken.append("heartbeat_recovery_metadata_updated")
            else:
                # Still in verification window
                result.actions_taken.append(
                    f"heartbeat_recovery_in_progress:{incident.recovery_success_count}/{RECOVERY_VERIFICATION_THRESHOLD}"
                )
                result.incident = incident
                logger.info(
                    "pipeline_heartbeat_recovery_in_progress",
                    incident_id=str(incident.id),
                    successes=incident.recovery_success_count,
                    required=RECOVERY_VERIFICATION_THRESHOLD,
                )

    async def _audit_pipeline_run(
        self,
        event: Event,
        result: PipelineResult,
        session: AsyncSession,
    ):
        """Record an audit log entry for the pipeline run."""
        audit = AuditLog(
            id=uuid.uuid4(),
            action="pipeline_processed",
            actor_type="system",
            resource_type="event",
            resource_id=str(event.id),
            project_id=event.project_id,
            incident_id=result.incident.id if result.incident else None,
            details={
                "event_type": event.event_type,
                "investigation_level": result.investigation_level.value,
                "actions_taken": result.actions_taken,
            },
            evidence={
                "fingerprint": result.fingerprint.fingerprint if result.fingerprint else None,
                "council_confidence": result.council_verdict.confidence if result.council_verdict else None,
                "policy_decision": result.policy_evaluation.decision.value if result.policy_evaluation else None,
            },
            authorization={"status": "automatic_pipeline"},
            outcome="success" if not result.errors else "partial_failure",
        )
        session.add(audit)


# Global pipeline orchestrator singleton
pipeline = PipelineOrchestrator()
