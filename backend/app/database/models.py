"""
hi.myrepo - Database Models

The immutable event spine and core entity models.
The UI does not own system state — the database does.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ============================================================================
# ENUMS
# ============================================================================

# Event Types
class EventType(str):
    # Heartbeat
    HEARTBEAT_SUCCESS = "HEARTBEAT_SUCCESS"
    HEARTBEAT_FAILURE = "HEARTBEAT_FAILURE"
    HEARTBEAT_DEGRADED = "HEARTBEAT_DEGRADED"
    # Error
    ERROR_DETECTED = "ERROR_DETECTED"
    ERROR_GROUP_UPDATED = "ERROR_GROUP_UPDATED"
    # Deployment
    DEPLOYMENT_STARTED = "DEPLOYMENT_STARTED"
    DEPLOYMENT_SUCCEEDED = "DEPLOYMENT_SUCCEEDED"
    DEPLOYMENT_FAILED = "DEPLOYMENT_FAILED"
    DEPLOYMENT_ROLLED_BACK = "DEPLOYMENT_ROLLED_BACK"
    # AI
    AI_REQUEST_STARTED = "AI_REQUEST_STARTED"
    AI_PROVIDER_FAILED = "AI_PROVIDER_FAILED"
    AI_PROVIDER_CASCADED = "AI_PROVIDER_CASCADED"
    AI_REQUEST_SUCCEEDED = "AI_REQUEST_SUCCEEDED"
    # Incident
    INCIDENT_CREATED = "INCIDENT_CREATED"
    INCIDENT_UPDATED = "INCIDENT_UPDATED"
    INCIDENT_ESCALATED = "INCIDENT_ESCALATED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"
    # Runbook
    RUNBOOK_PROPOSED = "RUNBOOK_PROPOSED"
    RUNBOOK_APPROVED = "RUNBOOK_APPROVED"
    RUNBOOK_STARTED = "RUNBOOK_STARTED"
    RUNBOOK_SUCCEEDED = "RUNBOOK_SUCCEEDED"
    RUNBOOK_FAILED = "RUNBOOK_FAILED"
    # Verification
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_SUCCEEDED = "VERIFICATION_SUCCEEDED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class Severity(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str):
    DETECTED = "DETECTED"
    TRIAGING = "TRIAGING"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    AWAITING_ACTION = "AWAITING_ACTION"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    REMEDIATION_FAILED = "REMEDIATION_FAILED"
    ESCALATED = "ESCALATED"


class IncidentStateTransition:
    """Valid state transitions for the incident state machine."""
    TRANSITIONS = {
        "DETECTED": ["TRIAGING"],
        "TRIAGING": ["INVESTIGATING"],
        "INVESTIGATING": ["DIAGNOSED", "TRIAGING"],
        "DIAGNOSED": ["AWAITING_ACTION"],
        "AWAITING_ACTION": ["REMEDIATING", "ESCALATED"],
        "REMEDIATING": ["VERIFYING", "REMEDIATION_FAILED"],
        "VERIFYING": ["RESOLVED", "REMEDIATION_FAILED"],
        "REMEDIATION_FAILED": ["ESCALATED"],
        "RESOLVED": [],
        "ESCALATED": [],
    }

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        return target in cls.TRANSITIONS.get(current, [])


class ProviderStatus(str):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class AutonomyLevel(int):
    OBSERVE = 0
    UNDERSTAND = 1
    RECOMMEND = 2
    GUARDED_ACTION = 3
    CONDITIONAL_AUTONOMY = 4


class RunbookStatus(str):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class RunbookExecutionStatus(str):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class VerificationStatus(str):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


# ============================================================================
# CORE MODELS
# ============================================================================


class Organization(Base):
    """Tenant boundary for multi-tenant isolation."""
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="organization")
    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class User(Base):
    """User account with organization membership."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="member")  # admin, member, viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    autonomy_level: Mapped[int] = mapped_column(Integer, default=AutonomyLevel.RECOMMEND)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="users")


class Project(Base):
    """A monitored application/project."""
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    repository_url: Mapped[str] = mapped_column(String(500), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    autonomy_level: Mapped[int] = mapped_column(Integer, default=AutonomyLevel.OBSERVE)
    monitoring_status: Mapped[str] = mapped_column(String(20), default="stopped")  # stopped, active
    monitoring_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    monitoring_stopped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_project_org_slug"),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="projects")
    environments: Mapped[list["Environment"]] = relationship(back_populates="project")
    events: Mapped[list["Event"]] = relationship(back_populates="project")
    error_groups: Mapped[list["ErrorGroup"]] = relationship(back_populates="project")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="project")
    deployments: Mapped[list["Deployment"]] = relationship(back_populates="project")
    dependencies: Mapped[list["Dependency"]] = relationship(back_populates="project")
    monitored_targets: Mapped[list["MonitoredTarget"]] = relationship(back_populates="project")


class Environment(Base):
    """Deployment environment for a project."""
    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # production, staging, development
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_env_project_name"),
    )

    project: Mapped["Project"] = relationship(back_populates="environments")


# ============================================================================
# EVENT SPINE — Immutable, timestamped, attributable, traceable, replayable,
# idempotent, correlation-aware
# ============================================================================


class Event(Base):
    """
    The immutable event spine. Every operational occurrence becomes an event.
    Events are never mutated — only appended.
    """
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # application, heartbeat, webhook, system
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    environment: Mapped[str] = mapped_column(String(50), default="production")
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True, index=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="events")
    incident: Mapped["Incident"] = relationship(back_populates="events")

    __table_args__ = (
        Index("idx_events_project_type_time", "project_id", "event_type", "received_at"),
        Index("idx_events_correlation", "correlation_id"),
        Index("idx_events_received_at", "received_at"),
    )


# ============================================================================
# ERROR FINGERPRINTING
# ============================================================================


class ErrorGroup(Base):
    """
    Deduplicated error groups via deterministic fingerprinting.
    182 identical errors → 1 error group → 1 incident.
    """
    __tablename__ = "error_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    error_type: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_stack: Mapped[str] = mapped_column(Text, nullable=True)
    route: Mapped[str] = mapped_column(String(500), nullable=True)
    file_location: Mapped[str] = mapped_column(String(500), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="error_groups")
    incident: Mapped["Incident"] = relationship(back_populates="error_groups")


# ============================================================================
# INCIDENT ENGINE
# ============================================================================


class Incident(Base):
    """
    Incidents have explicit state governed by a state machine.
    The UI does not own incident state — events do.
    """
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default=IncidentStatus.DETECTED, index=True)
    severity: Mapped[str] = mapped_column(String(20), default=Severity.MEDIUM)
    title: Mapped[str] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    affected_service: Mapped[str] = mapped_column(String(255), nullable=True)
    affected_component: Mapped[str] = mapped_column(String(255), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    blast_radius: Mapped[str] = mapped_column(String(20), nullable=True)  # low, medium, high, critical
    root_cause: Mapped[str] = mapped_column(Text, nullable=True)
    recommended_runbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbooks.id"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    # Recovery tracking (Phase I-I)
    recovery_success_count: Mapped[int] = mapped_column(Integer, default=0)
    recovery_verification_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="incidents")
    events: Mapped[list["Event"]] = relationship(back_populates="incident")
    error_groups: Mapped[list["ErrorGroup"]] = relationship(back_populates="incident")
    analyses: Mapped[list["IncidentAnalysis"]] = relationship(back_populates="incident")
    recommended_runbook: Mapped["Runbook"] = relationship(foreign_keys=[recommended_runbook_id])

    __table_args__ = (
        Index("idx_incidents_project_status", "project_id", "status"),
        Index("idx_incidents_severity_status", "severity", "status"),
    )


class IncidentAnalysis(Base):
    """
    Engineering Council analysis results for an incident.
    Each analysis records the council's verdict and evidence.
    """
    __tablename__ = "incident_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), index=True)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)  # council, single_ai, deterministic
    root_cause: Mapped[str] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    alternative_hypotheses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    blast_radius_assessment: Mapped[str] = mapped_column(String(20), nullable=True)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=True)
    risk_assessment: Mapped[str] = mapped_column(Text, nullable=True)
    required_verification: Mapped[str] = mapped_column(Text, nullable=True)
    council_rounds_used: Mapped[int] = mapped_column(Integer, default=0)
    council_budget_exceeded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    incident: Mapped["Incident"] = relationship(back_populates="analyses")


# ============================================================================
# DEPLOYMENTS
# ============================================================================


class Deployment(Base):
    """Deployment events correlated with incidents."""
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    environment: Mapped[str] = mapped_column(String(50), default="production")
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # started, succeeded, failed, rolled_back
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=True)
    commit_message: Mapped[str] = mapped_column(Text, nullable=True)
    branch: Mapped[str] = mapped_column(String(255), nullable=True)
    version: Mapped[str] = mapped_column(String(100), nullable=True)
    deployed_by: Mapped[str] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # github, vercel, manual, api
    deployment_url: Mapped[str] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="deployments")

    __table_args__ = (
        Index("idx_deployments_project_time", "project_id", "created_at"),
    )


# ============================================================================
# DEPENDENCIES
# ============================================================================


class Dependency(Base):
    """Tracked dependencies for a project."""
    __tablename__ = "dependencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # database, cache, api, service
    url: Mapped[str] = mapped_column(String(500), nullable=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped["Project"] = relationship(back_populates="dependencies")


# ============================================================================
# AI GATEWAY
# ============================================================================


class AIProvider(Base):
    """AI provider state — health, latency, usage, circuit breaker state."""
    __tablename__ = "ai_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # gemini, openai, groq
    status: Mapped[str] = mapped_column(String(20), default=ProviderStatus.UNKNOWN)
    success_rate: Mapped[float] = mapped_column(Float, default=1.0)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, default=0)
    recent_429_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    circuit_state: Mapped[str] = mapped_column(String(20), default="closed")  # closed, open, half_open
    capabilities: Mapped[list] = mapped_column(JSONB, default=list)  # text, vision, reasoning, code, speed
    models_available: Mapped[list] = mapped_column(JSONB, default=list)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=True)  # Encrypted API key
    configured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AIProviderEvent(Base):
    """Track individual AI provider invocations for observability."""
    __tablename__ = "ai_provider_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_providers.id"), index=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)  # council, investigation, analysis
    model_used: Mapped[str] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    tokens_input: Mapped[int] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    error_classification: Mapped[str] = mapped_column(String(50), nullable=True)  # retryable, non_retryable, policy
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ============================================================================
# RUNBOOKS
# ============================================================================


class Runbook(Base):
    """
    Explicitly defined operational procedures.
    AI can recommend runbooks. AI cannot invent arbitrary shell commands.
    """
    __tablename__ = "runbooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # e.g., RB-04
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=RunbookStatus.DRAFT)
    preconditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    authorization_requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    execution_steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rollback_strategy: Mapped[str] = mapped_column(Text, nullable=True)
    verification_procedure: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    max_blast_radius: Mapped[str] = mapped_column(String(20), default="medium")
    is_reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    required_autonomy_level: Mapped[int] = mapped_column(Integer, default=AutonomyLevel.GUARDED_ACTION)
    historical_success_count: Mapped[int] = mapped_column(Integer, default=0)
    historical_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class RunbookExecution(Base):
    """Record of runbook executions with approval chain."""
    __tablename__ = "runbook_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    runbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbooks.id"), index=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=RunbookExecutionStatus.PENDING)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=True)  # user_id or "policy_engine"
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    rollback_performed: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_trail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ============================================================================
# VERIFICATION
# ============================================================================


class VerificationRun(Base):
    """Post-remediation verification results."""
    __tablename__ = "verification_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), index=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbook_executions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=VerificationStatus.PENDING)
    verification_type: Mapped[str] = mapped_column(String(50), nullable=False)  # health_check, error_rate, custom
    checks_performed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    checks_passed: Mapped[int] = mapped_column(Integer, default=0)
    checks_failed: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ============================================================================
# INCIDENT MEMORY
# ============================================================================


class MemoryRecord(Base):
    """
    Historical memory of incidents, resolutions, and operational learnings.
    The system builds institutional knowledge over time.
    Every memory record belongs to a project for tenancy isolation.
    """
    __tablename__ = "memory_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # incident, resolution, postmortem, pattern
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=True)
    resolution: Mapped[str] = mapped_column(Text, nullable=True)
    runbook_code: Mapped[str] = mapped_column(String(20), nullable=True)
    confidence_at_resolution: Mapped[float] = mapped_column(Float, nullable=True)
    was_autonomous: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    embedding_vector: Mapped[list] = mapped_column(JSONB, nullable=True)  # for semantic search
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    project: Mapped["Project"] = relationship()

    __table_args__ = (
        Index("idx_memory_fingerprint", "fingerprint"),
        Index("idx_memory_category", "category"),
        Index("idx_memory_project_id", "project_id"),
    )


# ============================================================================
# MONITORED TARGETS (for heartbeat worker)
# ============================================================================


class MonitoredTarget(Base):
    """URL endpoints to be monitored by heartbeat workers."""
    __tablename__ = "monitored_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[int] = mapped_column(Integer, nullable=True)
    last_latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="monitored_targets")


# ============================================================================
# POLICY ENGINE
# ============================================================================


class Policy(Base):
    """
    Deterministic policy rules that control autonomy and authorization.
    AI proposes. Policy authorizes. Runbook executes.
    """
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # allow, deny, require_approval
    target_resource: Mapped[str] = mapped_column(String(100), nullable=False)  # runbook, incident, autonomy
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ============================================================================
# AUDIT LOGS
# ============================================================================


class AuditLog(Base):
    """
    Every consequential action must be recorded.
    WHO? WHAT? WHEN? WHY? BASED ON WHAT EVIDENCE? AUTHORIZED BY WHOM? EXECUTED HOW?
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)  # user, system, policy_engine, ai
    actor_id: Mapped[str] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    authorization: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    outcome: Mapped[str] = mapped_column(String(50), nullable=True)  # success, failure, denied
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_audit_actor_time", "actor_type", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )


# ============================================================================
# HEARTBEAT RESULTS
# ============================================================================


class HeartbeatResult(Base):
    """Results from heartbeat monitoring checks."""
    __tablename__ = "heartbeat_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitored_targets.id"), index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    response_headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
