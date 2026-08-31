"""
hi.myrepo - Telemetry Receiver Tests

Tests for telemetry ingestion, sanitization, and event conversion.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.telemetry.receiver import (
    TelemetryBatch,
    TelemetryPayload,
    TelemetryReceiver,
)


@pytest.fixture
def receiver():
    return TelemetryReceiver()


@pytest.fixture
def sample_batch():
    return TelemetryBatch(
        events=[
            TelemetryPayload(
                route="/api/checkout",
                timestamp=datetime.now(timezone.utc),
                error_message="TypeError: Cannot read property 'shippingMethod' of undefined",
                stack_trace="at CheckoutPage (checkout.js:42:10)",
                level="error",
                message="Checkout failed",
                project="ed-retail",
            ),
        ],
        project_id=uuid.uuid4(),
        source="browser",
        environment="production",
    )


class TestTelemetryPayload:
    def test_valid_payload(self):
        payload = TelemetryPayload(
            route="/api/test",
            timestamp=datetime.now(timezone.utc),
            level="error",
            message="Test error",
        )
        assert payload.level == "error"
        assert payload.project == ""

    def test_sanitize_api_key(self):
        payload = TelemetryPayload(
            route="/api/test",
            timestamp=datetime.now(timezone.utc),
            error_message="api_key=sk-1234567890abcdef request failed",
            level="error",
            message="auth failed",
        )
        # The validator should redact the API key
        assert "sk-1234567890abcdef" not in payload.error_message
        assert "REDACTED" in payload.error_message

    def test_sanitize_bearer_token(self):
        payload = TelemetryPayload(
            route="/api/test",
            timestamp=datetime.now(timezone.utc),
            error_message="Bearer eyJhbGciOiJIUzI1NiJ9.test",
            level="error",
            message="auth failed",
        )
        assert "eyJhbGciOiJIUzI1NiJ9.test" not in payload.error_message

    def test_sanitize_basic_auth(self):
        payload = TelemetryPayload(
            route="/api/test",
            timestamp=datetime.now(timezone.utc),
            error_message="Basic dXNlcjpwYXNz request failed",
            level="error",
            message="auth failed",
        )
        assert "dXNlcjpwYXNz" not in payload.error_message

    def test_level_defaults(self):
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="heartbeat",
        )
        assert payload.environment == "production"


class TestTelemetryBatch:
    def test_batch_defaults(self):
        batch = TelemetryBatch(
            events=[],
            project_id=uuid.uuid4(),
        )
        assert batch.source == "browser"
        assert batch.environment == "production"
        assert len(batch.events) == 0


class TestTelemetryReceiver:
    def test_max_batch_size(self):
        assert TelemetryReceiver.MAX_BATCH_SIZE == 50

    def test_max_event_size(self):
        assert TelemetryReceiver.MAX_EVENT_SIZE == 10_000

    @pytest.mark.asyncio
    async def test_receive_empty_batch(self, receiver):
        batch = TelemetryBatch(events=[], project_id=uuid.uuid4())
        result = await receiver.receive_batch(batch)
        assert result["processed"] == 0
        assert result["errors"] == 0
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_receive_valid_batch(self, receiver, sample_batch):
        result = await receiver.receive_batch(sample_batch)
        assert result["processed"] == 1
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_receive_truncates_large_batch(self, receiver):
        events = [
            TelemetryPayload(
                route="/",
                timestamp=datetime.now(timezone.utc),
                level="info",
                message="test",
            )
            for _ in range(100)
        ]
        batch = TelemetryBatch(events=events, project_id=uuid.uuid4())
        result = await receiver.receive_batch(batch)
        # Should be truncated to MAX_BATCH_SIZE
        assert result["total"] <= TelemetryReceiver.MAX_BATCH_SIZE

    def test_map_error_level(self, receiver):
        assert receiver._map_telemetry_to_event_type(
            TelemetryPayload(route="/", timestamp=datetime.now(timezone.utc), level="error", message="x")
        ) == "ERROR_DETECTED"

    def test_map_critical_level(self, receiver):
        assert receiver._map_telemetry_to_event_type(
            TelemetryPayload(route="/", timestamp=datetime.now(timezone.utc), level="critical", message="x")
        ) == "ERROR_DETECTED"

    def test_map_info_level(self, receiver):
        assert receiver._map_telemetry_to_event_type(
            TelemetryPayload(route="/", timestamp=datetime.now(timezone.utc), level="info", message="x")
        ) == "HEARTBEAT_SUCCESS"

    def test_severity_mapping(self, receiver):
        assert receiver._map_telemetry_to_severity(
            TelemetryPayload(route="/", timestamp=datetime.now(timezone.utc), level="critical", message="x")
        ) == "critical"
        assert receiver._map_telemetry_to_severity(
            TelemetryPayload(route="/", timestamp=datetime.now(timezone.utc), level="error", message="x")
        ) == "high"
        assert receiver._map_telemetry_to_severity(
            TelemetryPayload(route="/", timestamp=datetime.now(timezone.utc), level="warning", message="x")
        ) == "medium"
        assert receiver._map_telemetry_to_severity(
            TelemetryPayload(route="/", timestamp=datetime.now(timezone.utc), level="info", message="x")
        ) == "low"
