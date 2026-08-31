"""
Tests for Event Spine

The event spine is the architectural core.
Every operational occurrence becomes an event.
Events are never mutated — only appended.
"""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.events.spine import EventEnvelope


class TestEventEnvelope:
    """Test event envelope validation."""

    def _make_envelope(self, **overrides):
        defaults = {
            "event_type": "ERROR_DETECTED",
            "occurred_at": datetime.now(timezone.utc),
            "source": "test-app",
            "source_type": "application",
            "project_id": uuid.uuid4(),
        }
        defaults.update(overrides)
        return EventEnvelope(**defaults)

    def test_valid_envelope(self):
        """A properly formed envelope should be accepted."""
        envelope = self._make_envelope()
        assert envelope.event_type == "ERROR_DETECTED"

    def test_rejects_invalid_event_type(self):
        """Invalid event types should be rejected."""
        with pytest.raises(ValidationError):
            self._make_envelope(event_type="INVALID_TYPE")

    def test_all_valid_event_types_accepted(self):
        """All defined event types should be valid."""
        valid_types = [
            "HEARTBEAT_SUCCESS", "HEARTBEAT_FAILURE", "HEARTBEAT_DEGRADED",
            "ERROR_DETECTED", "ERROR_GROUP_UPDATED",
            "DEPLOYMENT_STARTED", "DEPLOYMENT_SUCCEEDED", "DEPLOYMENT_FAILED",
            "DEPLOYMENT_ROLLED_BACK",
            "AI_REQUEST_STARTED", "AI_PROVIDER_FAILED", "AI_PROVIDER_CASCADED",
            "AI_REQUEST_SUCCEEDED",
            "INCIDENT_CREATED", "INCIDENT_UPDATED", "INCIDENT_ESCALATED",
            "INCIDENT_RESOLVED",
            "RUNBOOK_PROPOSED", "RUNBOOK_APPROVED", "RUNBOOK_STARTED",
            "RUNBOOK_SUCCEEDED", "RUNBOOK_FAILED",
            "VERIFICATION_STARTED", "VERIFICATION_SUCCEEDED", "VERIFICATION_FAILED",
        ]
        for event_type in valid_types:
            envelope = self._make_envelope(event_type=event_type)
            assert envelope.event_type == event_type

    def test_rejects_empty_event_type(self):
        """Event type cannot be empty."""
        with pytest.raises(ValidationError):
            self._make_envelope(event_type="")

    def test_rejects_invalid_severity(self):
        """Invalid severity should be rejected."""
        with pytest.raises(ValidationError):
            self._make_envelope(severity="extreme")

    def test_valid_severities_accepted(self):
        """All valid severity levels should be accepted."""
        for severity in ["low", "medium", "high", "critical"]:
            envelope = self._make_envelope(severity=severity)
            assert envelope.severity == severity

    def test_severity_is_normalized_to_lowercase(self):
        """Severity should be normalized to lowercase."""
        envelope = self._make_envelope(severity="HIGH")
        assert envelope.severity == "high"

    def test_rejects_invalid_source_type(self):
        """Invalid source type should be rejected."""
        with pytest.raises(ValidationError):
            self._make_envelope(source_type="invalid")

    def test_valid_source_types_accepted(self):
        """All valid source types should be accepted."""
        for source_type in ["application", "heartbeat", "webhook", "system", "worker"]:
            envelope = self._make_envelope(source_type=source_type)
            assert envelope.source_type == source_type

    def test_optional_fields_default(self):
        """Optional fields should have sensible defaults."""
        envelope = self._make_envelope()
        assert envelope.environment == "production"
        assert envelope.schema_version == 1
        assert envelope.correlation_id is None
        assert envelope.trace_id is None
        assert envelope.severity is None
        assert envelope.payload == {}
        assert envelope.metadata == {}

    def test_payload_and_metadata_populated(self):
        """Payload and metadata should be stored correctly."""
        envelope = self._make_envelope(
            payload={"error": "test", "code": 500},
            metadata={"source": "test"},
        )
        assert envelope.payload["error"] == "test"
        assert envelope.metadata["source"] == "test"

    def test_correlation_id_preserved(self):
        """Correlation IDs should be preserved."""
        cid = uuid.uuid4()
        envelope = self._make_envelope(correlation_id=cid)
        assert envelope.correlation_id == cid

    def test_trace_id_preserved(self):
        """Trace IDs should be preserved."""
        tid = uuid.uuid4()
        envelope = self._make_envelope(trace_id=tid)
        assert envelope.trace_id == tid
