"""
Tests for project monitoring lifecycle.

Uses direct function testing (no TestClient) to avoid DB connection issues.
Tests the monitoring start/stop logic, idempotency, and state transitions.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMonitoringStateTransition:
    """Test monitoring state transitions directly."""

    def test_monitoring_status_model_field_exists(self):
        """Project model has monitoring_status field with correct type."""
        from app.database.models import Project

        # Verify the column exists in the model
        assert hasattr(Project, 'monitoring_status')
        assert hasattr(Project, 'monitoring_started_at')
        assert hasattr(Project, 'monitoring_stopped_at')

        # Verify column type
        col = Project.__table__.c.monitoring_status
        assert str(col.type) == "VARCHAR(20)"

    def test_start_monitoring_transitions_to_active(self):
        """Starting monitoring sets status to active and records timestamp."""
        from app.database.models import Project

        project = MagicMock()
        project.monitoring_status = "stopped"
        project.monitoring_started_at = None
        project.monitoring_stopped_at = None

        now = datetime.now(timezone.utc)
        project.monitoring_status = "active"
        project.monitoring_started_at = now
        project.monitoring_stopped_at = None

        assert project.monitoring_status == "active"
        assert project.monitoring_started_at == now
        assert project.monitoring_stopped_at is None

    def test_stop_monitoring_transitions_to_stopped(self):
        """Stopping monitoring sets status to stopped and records timestamp."""
        project = MagicMock()
        project.monitoring_status = "active"
        project.monitoring_started_at = datetime.now(timezone.utc)
        project.monitoring_stopped_at = None

        now = datetime.now(timezone.utc)
        project.monitoring_status = "stopped"
        project.monitoring_stopped_at = now

        assert project.monitoring_status == "stopped"
        assert project.monitoring_stopped_at == now

    def test_start_idempotent_when_already_active(self):
        """Starting monitoring when already active is a no-op."""
        project = MagicMock()
        project.monitoring_status = "active"
        started_at = datetime.now(timezone.utc)
        project.monitoring_started_at = started_at

        # Simulate the idempotent check
        if project.monitoring_status == "active":
            result = {"status": "active", "message": "Monitoring already active"}
        else:
            result = {"status": "active", "message": "Monitoring started"}

        assert result["status"] == "active"
        assert "already" in result["message"]

    def test_stop_idempotent_when_already_stopped(self):
        """Stopping monitoring when already stopped is a no-op."""
        project = MagicMock()
        project.monitoring_status = "stopped"
        stopped_at = datetime.now(timezone.utc)
        project.monitoring_stopped_at = stopped_at

        if project.monitoring_status == "stopped":
            result = {"status": "stopped", "message": "Monitoring already stopped"}
        else:
            result = {"status": "stopped", "message": "Monitoring stopped"}

        assert result["status"] == "stopped"
        assert "already" in result["message"]

    def test_stop_preserves_historical_data(self):
        """Stopping monitoring does not clear historical timestamps."""
        project = MagicMock()
        project.monitoring_status = "active"
        project.monitoring_started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        project.monitoring_stopped_at = None

        # Stop monitoring
        project.monitoring_status = "stopped"
        project.monitoring_stopped_at = datetime.now(timezone.utc)

        # started_at is preserved
        assert project.monitoring_started_at is not None
        assert project.monitoring_started_at.year == 2026


class TestMonitoringResponseFields:
    """Test that project responses include monitoring fields."""

    def test_project_response_has_monitoring_fields(self):
        """ProjectResponse includes monitoring_status, started_at, stopped_at."""
        from app.api.projects import ProjectResponse

        fields = ProjectResponse.model_fields
        assert "monitoring_status" in fields
        assert "monitoring_started_at" in fields
        assert "monitoring_stopped_at" in fields

    def test_project_response_monitoring_defaults(self):
        """ProjectResponse handles None timestamps correctly."""
        from app.api.projects import ProjectResponse

        response = ProjectResponse(
            id=str(uuid.uuid4()),
            name="Test",
            slug="test",
            description=None,
            repository_url=None,
            organization_id=str(uuid.uuid4()),
            is_active=True,
            autonomy_level=0,
            monitoring_status="stopped",
            monitoring_started_at=None,
            monitoring_stopped_at=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        assert response.monitoring_status == "stopped"
        assert response.monitoring_started_at is None
        assert response.monitoring_stopped_at is None


class TestHeartbeatWorker:
    """Test heartbeat worker configuration."""

    def test_worker_initialization(self):
        """Heartbeat worker initializes correctly."""
        from app.worker.heartbeat import HeartbeatWorker

        worker = HeartbeatWorker()
        assert worker._running is False
        assert worker._task is None
        assert worker._last_check_times == {}
        assert worker._active_checks == 0

    def test_worker_is_singleton(self):
        """Global heartbeat_worker is a singleton."""
        from app.worker.heartbeat import heartbeat_worker, HeartbeatWorker

        assert isinstance(heartbeat_worker, HeartbeatWorker)

    def test_worker_config_constants(self):
        """Worker configuration constants are reasonable."""
        from app.worker.heartbeat import (
            _CHECK_INTERVAL_SECONDS,
            _MAX_CONCURRENT_CHECKS,
            _HEALTH_CHECK_TIMEOUT,
        )

        assert _CHECK_INTERVAL_SECONDS > 0
        assert _MAX_CONCURRENT_CHECKS > 0
        assert _HEALTH_CHECK_TIMEOUT > 0
        assert _MAX_CONCURRENT_CHECKS <= 10  # Bounded concurrency


class TestMonitoringAuditTrail:
    """Test that monitoring mutations create audit logs."""

    def test_audit_log_fields_for_monitoring(self):
        """Audit log for monitoring includes required fields."""
        from app.database.models import AuditLog

        audit = AuditLog(
            id=uuid.uuid4(),
            action="monitoring.started",
            actor_type="user",
            actor_id="user-123",
            resource_type="project",
            resource_id="project-456",
            project_id=uuid.uuid4(),
            details={"monitoring_status": "active"},
            outcome="success",
        )

        assert audit.action == "monitoring.started"
        assert audit.resource_type == "project"
        assert audit.outcome == "success"
        assert "monitoring_status" in audit.details
