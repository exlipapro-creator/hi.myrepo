"""
Tests for monitored targets API.
"""
import uuid

import pytest
from pydantic import ValidationError

from app.api.monitored_targets import (
    MonitoredTargetCreate,
    MonitoredTargetResponse,
    MonitoredTargetUpdate,
)


class TestMonitoredTargetCreate:
    """Test target creation model."""

    def test_valid_target(self):
        target = MonitoredTargetCreate(
            project_id=uuid.uuid4(),
            name="API Health",
            url="https://example.com/health",
        )
        assert target.method == "GET"
        assert target.expected_status == 200
        assert target.timeout_seconds == 10
        assert target.interval_seconds == 60

    def test_custom_method(self):
        target = MonitoredTargetCreate(
            project_id=uuid.uuid4(),
            name="API Check",
            url="https://example.com/api/status",
            method="POST",
            expected_status=200,
        )
        assert target.method == "POST"


class TestMonitoredTargetUpdate:
    """Test target update model."""

    def test_partial_update(self):
        update = MonitoredTargetUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.url is None
        assert update.is_active is None

    def test_active_toggle(self):
        update = MonitoredTargetUpdate(is_active=False)
        assert update.is_active is False


class TestMonitoredTargetResponse:
    """Test target response model."""

    def test_response_fields(self):
        resp = MonitoredTargetResponse(
            id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            name="Health Check",
            url="https://example.com",
            method="GET",
            expected_status=200,
            timeout_seconds=10,
            interval_seconds=60,
            is_active=True,
            last_check_at=None,
            last_status=None,
            last_latency_ms=None,
            is_degraded=False,
            created_at="2026-01-01T00:00:00Z",
        )
        assert resp.is_active is True
        assert resp.is_degraded is False
        assert resp.last_status is None
