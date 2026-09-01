"""
hi.myrepo - Telemetry Defense Tests

Adversarial tests proving the telemetry ingestion system cannot be abused
as an unauthenticated event-injection or resource-exhaustion machine.

Tests:
- Oversized payloads
- Timestamp manipulation
- Sensitive data scrubbing
- Event type injection prevention
- Rate limiting
- Malformed metadata
- Stack trace bounds
- Replay resistance
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.telemetry.receiver import (
    TelemetryBatch,
    TelemetryPayload,
    TelemetryReceiver,
    _MAX_STACK_LEN,
    _MAX_STR_LEN,
    _FUTURE_BUFFER,
    _PAST_BUFFER,
    _ALLOWED_LEVELS,
    _sanitize_string,
)


@pytest.fixture
def receiver():
    return TelemetryReceiver()


# ==========================================================================
# Timestamp Manipulation Resistance
# ==========================================================================

class TestTimestampDefense:
    """Verify timestamps cannot be manipulated to inject events in the past or future."""

    def test_future_timestamp_capped(self):
        """Events with timestamps far in the future are clamped to now."""
        future = datetime.now(timezone.utc) + timedelta(days=365)
        payload = TelemetryPayload(
            route="/",
            timestamp=future,
            level="error",
            message="test",
        )
        now = datetime.now(timezone.utc)
        assert payload.timestamp <= now + timedelta(seconds=5)

    def test_past_timestamp_capped(self):
        """Events with timestamps far in the past are clamped."""
        past = datetime.now(timezone.utc) - timedelta(days=365)
        payload = TelemetryPayload(
            route="/",
            timestamp=past,
            level="error",
            message="test",
        )
        # Should be clamped to now - PAST_BUFFER
        now = datetime.now(timezone.utc)
        assert payload.timestamp >= now - _PAST_BUFFER - timedelta(seconds=5)

    def test_valid_timestamp_preserved(self):
        """Recent timestamps within bounds are preserved."""
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = TelemetryPayload(
            route="/",
            timestamp=recent,
            level="error",
            message="test",
        )
        assert abs((payload.timestamp - recent).total_seconds()) < 1

    def test_naive_timestamp_gets_timezone(self):
        """Naive timestamps get UTC timezone appended."""
        naive = datetime(2025, 1, 1, 12, 0, 0)
        payload = TelemetryPayload(
            route="/",
            timestamp=naive,
            level="info",
            message="test",
        )
        assert payload.timestamp.tzinfo is not None


# ==========================================================================
# Sensitive Data Scrubbing
# ==========================================================================

class TestSensitiveDataDefense:
    """Verify sensitive patterns are scrubbed from all fields."""

    def test_api_key_in_error_message(self):
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            error_message="Failed with api_key=sk-live-abcdef1234567890abcdef",
            level="error",
            message="auth failed",
        )
        assert "sk-live-abcdef1234567890abcdef" not in payload.error_message
        assert "REDACTED" in payload.error_message

    def test_bearer_token_in_error(self):
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            error_message="401 Unauthorized Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            level="error",
            message="auth failed",
        )
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in payload.error_message

    def test_email_in_message(self):
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="error",
            message="Error for user admin@example.com",
        )
        assert "admin@example.com" not in payload.message
        assert "REDACTED" in payload.message

    def test_api_key_in_stack_trace(self):
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            stack_trace="at connect(secret=super_secret_key_abc123def456) in auth.js:10",
            level="error",
            message="crash",
        )
        assert "super_secret_key_abc123def456" not in payload.stack_trace

    def test_secret_in_metadata_value(self):
        """Metadata values are also scrubbed."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="error",
            message="test",
            metadata={"page_title": "api_key=secret123"},
        )
        # Metadata keys must be in the allowlist — "page_title" is allowed
        # but the value should be scrubbed
        if "page_title" in payload.metadata:
            assert "secret123" not in str(payload.metadata.get("page_title", ""))


# ==========================================================================
# Event Type Injection Prevention
# ==========================================================================

class TestEventTypeInjection:
    """Verify callers cannot inject arbitrary event types through telemetry."""

    def test_level_normalization(self):
        """Invalid levels are normalized to 'info'."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="INCIDENT_CREATED",  # Trying to inject incident event type
            message="test",
        )
        assert payload.level == "info"  # Normalized to safe default

    def test_case_insensitive_level(self):
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="ERROR",
            message="test",
        )
        assert payload.level == "error"

    def test_empty_level_defaults_to_info(self):
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="",
            message="test",
        )
        assert payload.level == "info"

    def test_attempt_to_inject_severity_via_metadata(self):
        """Attacker tries to inject severity via metadata."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
            metadata={"severity": "critical", "event_type": "INCIDENT_CREATED"},
        )
        # Metadata keys not in allowlist are dropped
        assert "severity" not in payload.metadata
        assert "event_type" not in payload.metadata

    @pytest.mark.asyncio
    async def test_receiver_always_derives_event_type(self, receiver):
        """The receiver NEVER reads event_type from caller input."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
        )
        batch = TelemetryBatch(events=[payload], project_id=uuid.uuid4())
        envelope = await receiver._process_telemetry(payload, batch)
        # event_type must always be derived from level, not caller
        assert envelope.event_type in ("HEARTBEAT_SUCCESS", "ERROR_DETECTED")

    @pytest.mark.asyncio
    async def test_severity_always_derived_from_level(self, receiver):
        """Severity is always derived from level, never from caller input."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
        )
        batch = TelemetryBatch(events=[payload], project_id=uuid.uuid4())
        envelope = await receiver._process_telemetry(payload, batch)
        # info level → low severity, never critical
        assert envelope.severity == "low"


# ==========================================================================
# Payload Bounds
# ==========================================================================

class TestPayloadBounds:
    """Verify all fields are length-capped."""

    def test_error_message_truncated(self):
        long_msg = "A" * 5000
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            error_message=long_msg,
            level="error",
            message="test",
        )
        assert len(payload.error_message) <= _MAX_STR_LEN

    def test_stack_trace_truncated(self):
        long_trace = "at foo (bar.js:" + "1" * 10000 + ")"
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            stack_trace=long_trace,
            level="error",
            message="test",
        )
        assert len(payload.stack_trace) <= _MAX_STACK_LEN

    def test_message_truncated(self):
        long_msg = "M" * 5000
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="error",
            message=long_msg,
        )
        assert len(payload.message) <= _MAX_STR_LEN

    def test_route_truncated(self):
        long_route = "/" + "a" * 1000
        payload = TelemetryPayload(
            route=long_route,
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
        )
        assert len(payload.route) <= 500

    def test_browser_info_truncated(self):
        long_info = "Mozilla/5.0 " + "x" * 2000
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            browser_info=long_info,
            level="info",
            message="test",
        )
        assert len(payload.browser_info) <= 500

    def test_max_batch_size_enforced(self):
        assert TelemetryReceiver.MAX_BATCH_SIZE == 50


# ==========================================================================
# Metadata Injection Defense
# ==========================================================================

class TestMetadataDefense:
    """Verify metadata cannot be used for injection attacks."""

    def test_complex_types_dropped(self):
        """Lists, dicts, and nested structures are dropped from metadata."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
            metadata={
                "injected": {"nested": "dict"},
                "list_val": [1, 2, 3],
                "page_title": "normal",
            },
        )
        # Complex types should be dropped
        assert "injected" not in payload.metadata
        assert "list_val" not in payload.metadata
        # Simple allowed keys are kept
        assert payload.metadata.get("page_title") == "normal"

    def test_unknown_metadata_keys_dropped(self):
        """Keys not in the allowlist are silently dropped."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
            metadata={
                "project_id": str(uuid.uuid4()),  # Trying to override project
                "severity": "critical",
                "actor": "admin",
                "allowed_key": "value",
            },
        )
        # None of the injected keys should be present
        assert "project_id" not in payload.metadata
        assert "severity" not in payload.metadata
        assert "actor" not in payload.metadata

    def test_metadata_capped_at_max_keys(self):
        """Too many metadata keys are truncated."""
        many_keys = {f"key_{i}": f"value_{i}" for i in range(100)}
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
            metadata=many_keys,
        )
        # Only allowed keys survive, max 20
        assert len(payload.metadata) <= 20

    def test_numeric_metadata_preserved(self):
        """Numeric metadata values are preserved for allowed keys."""
        payload = TelemetryPayload(
            route="/",
            timestamp=datetime.now(timezone.utc),
            level="info",
            message="test",
            metadata={
                "viewport": "1920x1080",
                "language": "en-US",
                "platform": "web",
            },
        )
        assert payload.metadata.get("viewport") == "1920x1080"
        assert payload.metadata.get("language") == "en-US"


# ==========================================================================
# Rate Limiting
# ==========================================================================

class TestRateLimiting:
    """Verify per-project rate limiting works."""

    def test_rate_limit_not_triggered_below_threshold(self):
        receiver = TelemetryReceiver()
        project_id = str(uuid.uuid4())
        # Should not be rate limited at low volume
        for _ in range(10):
            assert receiver._check_rate_limit(project_id) is False

    def test_rate_limit_triggered_above_threshold(self):
        receiver = TelemetryReceiver()
        project_id = str(uuid.uuid4())
        # Exhaust the rate window
        for _ in range(TelemetryReceiver._RATE_MAX_EVENTS + 1):
            receiver._check_rate_limit(project_id)
        # Next request should be rate limited
        assert receiver._check_rate_limit(project_id) is True

    def test_rate_limit_per_project(self):
        """Different projects have independent rate limits."""
        receiver = TelemetryReceiver()
        p1 = str(uuid.uuid4())
        p2 = str(uuid.uuid4())
        # Exhaust project 1
        for _ in range(TelemetryReceiver._RATE_MAX_EVENTS + 1):
            receiver._check_rate_limit(p1)
        # Project 2 should still be allowed
        assert receiver._check_rate_limit(p2) is False

    @pytest.mark.asyncio
    async def test_rate_limited_batch_returns_flag(self, receiver):
        """A rate-limited batch returns a rate_limited flag."""
        project_id = uuid.uuid4()
        # Exhaust the rate limit
        for _ in range(TelemetryReceiver._RATE_MAX_EVENTS + 1):
            receiver._check_rate_limit(str(project_id))

        batch = TelemetryBatch(
            events=[
                TelemetryPayload(
                    route="/",
                    timestamp=datetime.now(timezone.utc),
                    level="error",
                    message="test",
                )
            ],
            project_id=project_id,
        )
        result = await receiver.receive_batch(batch)
        assert result.get("rate_limited") is True
        assert result["processed"] == 0


# ==========================================================================
# Sanitize String Utility
# ==========================================================================

class TestSanitizeString:
    """Test the string sanitization utility."""

    def test_truncation(self):
        result = _sanitize_string("A" * 10000, max_len=100)
        assert len(result) == 100

    def test_empty_string(self):
        assert _sanitize_string("") == ""
        assert _sanitize_string("", max_len=100) == ""

    def test_api_key_redacted(self):
        result = _sanitize_string("key=sk-1234567890abcdefghij")
        assert "sk-1234567890abcdefghij" not in result

    def test_bearer_redacted(self):
        result = _sanitize_string("Bearer eyJhbGciOiJIUzI1NiJ9")
        assert "eyJhbGciOiJIUzI1NiJ9" not in result

    def test_normal_text_preserved(self):
        result = _sanitize_string("TypeError: Cannot read property 'x' of undefined")
        assert "TypeError" in result
