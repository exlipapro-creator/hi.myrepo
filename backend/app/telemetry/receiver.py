"""
hi.myrepo - Telemetry Receiver

Zero-SDK telemetry using navigator.sendBeacon().
Captures useful operational information with a sanitization boundary.

Must NOT capture: passwords, tokens, payment credentials, secrets, PII.

Security constraints enforced here:
- All string fields are length-capped
- Timestamps are bounded (±24 hours from now)
- Metadata keys are allowlisted
- Stack traces are truncated
- Secret patterns are scrubbed
- event_type is not caller-controllable (mapped deterministically from level)
- Severity is not caller-controllable (mapped deterministically from level)
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.events.spine import EventEnvelope, event_processor

# Maximum field lengths
_MAX_STR_LEN = 2_000       # General string fields
_MAX_STACK_LEN = 5_000     # Stack traces can be longer but still bounded
_MAX_MESSAGE_LEN = 2_000
_MAX_ROUTE_LEN = 500
_MAX_BROWSER_INFO_LEN = 500
_MAX_METADATA_KEYS = 20
_MAX_METADATA_VALUE_LEN = 500

# Timestamp bounds — reject events more than 24 hours in the future
# or more than 7 days in the past
_FUTURE_BUFFER = timedelta(hours=24)
_PAST_BUFFER = timedelta(days=7)

# Sensitive patterns to scrub
_SENSITIVE_PATTERNS = [
    (re.compile(r"(?:api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+", re.IGNORECASE), "[REDACTED]"),
    (re.compile(r"Bearer\s+\S+"), "Bearer [REDACTED]"),
    (re.compile(r"Basic\s+\S+"), "Basic [REDACTED]"),
    (re.compile(r"(?:sk|pk|rk|ak)[-_][a-zA-Z0-9]{20,}"), "[REDACTED_KEY]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED_EMAIL]"),
]

# Allowed event types that telemetry can generate (telemetry never decides)
_ALLOWED_LEVELS = {"info", "warning", "error", "critical"}

# Allowed metadata keys (prevent injection of arbitrary internal fields)
_ALLOWED_METADATA_KEYS = {
    "page_title", "viewport", "session_id", "user_agent_segment",
    "connection_type", "language", "platform", "screen_size",
}



def _sanitize_string(v: str, max_len: int = _MAX_STR_LEN) -> str:
    """Truncate and scrub sensitive patterns from a string."""
    if not v:
        return v
    # Truncate first to avoid wasting regex time on huge payloads
    v = v[:max_len]
    for pattern, replacement in _SENSITIVE_PATTERNS:
        v = pattern.sub(replacement, v)
    return v


class TelemetryPayload(BaseModel):
    """
    Client telemetry payload.
    Sent via navigator.sendBeacon() from the frontend.

    All fields are length-capped. Timestamps are bounded.
    Event type and severity are derived deterministically from level.
    """
    route: str = Field(default="")
    timestamp: datetime
    error_message: Optional[str] = Field(default=None)
    stack_trace: Optional[str] = Field(default=None)
    browser_info: Optional[str] = Field(default=None)
    runtime: Optional[str] = Field(default=None)
    release: Optional[str] = Field(default=None)
    version: Optional[str] = Field(default=None)
    project: str = Field(default="")
    environment: str = Field(default="production")
    correlation_id: Optional[str] = Field(default=None)
    level: str = Field(default="info")
    message: str = Field(default="")
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_telemetry(self) -> "TelemetryPayload":
        """Enforce security constraints on the full payload."""
        # 1. Normalize and validate level
        normalized_level = self.level.lower().strip()
        if normalized_level not in _ALLOWED_LEVELS:
            normalized_level = "info"
        self.level = normalized_level

        # 2. Timestamp bounds — reject events too far in the past or future
        now = datetime.now(timezone.utc)
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts > now + _FUTURE_BUFFER:
            self.timestamp = now
        elif ts < now - _PAST_BUFFER:
            self.timestamp = now - _PAST_BUFFER
        else:
            self.timestamp = ts

        # 3. Sanitize all string fields
        self.route = _sanitize_string(self.route, _MAX_ROUTE_LEN)
        self.message = _sanitize_string(self.message, _MAX_MESSAGE_LEN)
        self.project = _sanitize_string(self.project, 100)
        self.environment = _sanitize_string(self.environment, 50)

        if self.error_message:
            self.error_message = _sanitize_string(self.error_message, _MAX_STR_LEN)
        if self.stack_trace:
            self.stack_trace = _sanitize_string(self.stack_trace, _MAX_STACK_LEN)
        if self.browser_info:
            self.browser_info = _sanitize_string(self.browser_info, _MAX_BROWSER_INFO_LEN)
        if self.release:
            self.release = _sanitize_string(self.release, 100)
        if self.version:
            self.version = _sanitize_string(self.version, 50)

        # 4. Sanitize metadata — allowlist keys, cap values, cap count
        if self.metadata:
            sanitized = {}
            for k, v in list(self.metadata.items())[:_MAX_METADATA_KEYS]:
                clean_key = str(k)[:100]
                if clean_key not in _ALLOWED_METADATA_KEYS:
                    continue
                if isinstance(v, str):
                    sanitized[clean_key] = _sanitize_string(v, _MAX_METADATA_VALUE_LEN)
                elif isinstance(v, (int, float, bool)):
                    sanitized[clean_key] = v
                # Drop complex types (lists, dicts) from metadata
            self.metadata = sanitized
        else:
            self.metadata = {}

        # 5. Validate correlation_id format
        if self.correlation_id:
            try:
                uuid.UUID(self.correlation_id)
            except ValueError:
                self.correlation_id = None

        # 6. Validate runtime enum
        allowed_runtimes = {"browser", "node", "edge", "server", "mobile", ""}
        if self.runtime and self.runtime.lower() not in allowed_runtimes:
            self.runtime = "unknown"

        return self


class TelemetryBatch(BaseModel):
    """Batch of telemetry events."""
    events: list[TelemetryPayload] = Field(default_factory=list)
    project_id: uuid.UUID
    source: str = "browser"
    environment: str = "production"


class TelemetryReceiver:
    """
    Receives and processes telemetry from clients.
    Sanitizes input, creates events, and persists them.

    Security constraints:
    - Batch size capped at MAX_BATCH_SIZE
    - Per-event size is bounded by Pydantic model validators
    - Rate limiting via sliding window per project
    - Event type is derived from level (not caller-controlled)
    - Severity is derived from level (not caller-controlled)
    - Idempotency keys prevent duplicate event creation
    """

    # Maximum payload size to prevent abuse
    MAX_BATCH_SIZE = 50
    MAX_EVENT_SIZE = 10_000  # characters

    # Rate limiting: per-project sliding window
    # {project_id: [(timestamp, count), ...]}
    _rate_windows: dict[str, list] = {}
    _RATE_WINDOW_SECONDS = 60  # 1 minute window
    _RATE_MAX_EVENTS = 200     # max events per window per project

    def _check_rate_limit(self, project_id: str) -> bool:
        """Check if a project has exceeded its telemetry rate limit.
        Returns True if the request should be rejected.
        """
        import time
        now = time.time()
        window_key = str(project_id)

        if window_key not in self._rate_windows:
            self._rate_windows[window_key] = []

        # Prune old entries outside the window
        window = self._rate_windows[window_key]
        cutoff = now - self._RATE_WINDOW_SECONDS
        self._rate_windows[window_key] = [ts for ts in window if ts > cutoff]

        if len(self._rate_windows[window_key]) >= self._RATE_MAX_EVENTS:
            return True  # Rate limited

        self._rate_windows[window_key].append(now)
        return False

    async def receive_batch(self, batch: TelemetryBatch, session=None) -> dict:
        """
        Process a batch of telemetry events.
        If a session is provided, events are persisted to the event spine.
        Returns a summary of processed events.
        """
        processed = 0
        errors = 0
        rate_limited = 0

        # Check rate limit for this project
        if self._check_rate_limit(str(batch.project_id)):
            return {
                "processed": 0,
                "errors": 0,
                "total": 0,
                "rate_limited": True,
            }

        # Limit batch size
        events = batch.events[:self.MAX_BATCH_SIZE]

        for telemetry in events:
            try:
                envelope = await self._process_telemetry(telemetry, batch)
                if session and envelope:
                    from app.events.spine import event_processor
                    await event_processor.process_event(envelope, session)
                processed += 1
            except Exception:
                errors += 1

        return {
            "processed": processed,
            "errors": errors,
            "total": len(events),
        }

    async def _process_telemetry(
        self,
        telemetry: TelemetryPayload,
        batch: TelemetryBatch,
    ) -> None:
        """Process a single telemetry event.

        CRITICAL: Event type and severity are NEVER caller-controlled.
        They are always derived deterministically from the level field.
        The caller cannot inject arbitrary event types via metadata or payload.
        """
        # Event type and severity are deterministic — derived from level
        event_type = self._map_telemetry_to_event_type(telemetry)
        severity = self._map_telemetry_to_severity(telemetry)

        # correlation_id is already validated by the Pydantic model
        correlation_id = None
        if telemetry.correlation_id:
            try:
                correlation_id = uuid.UUID(telemetry.correlation_id)
            except ValueError:
                pass

        # Build payload — never include raw caller-controlled event_type
        payload = {
            "route": telemetry.route,
            "error_message": telemetry.error_message,
            "stack_trace": telemetry.stack_trace,
            "browser_info": telemetry.browser_info,
            "runtime": telemetry.runtime,
            "release": telemetry.release,
            "version": telemetry.version,
            "level": telemetry.level,
            "message": telemetry.message,
        }

        envelope = EventEnvelope(
            event_type=event_type,
            occurred_at=telemetry.timestamp,
            source=telemetry.project or batch.source,
            source_type="application",
            project_id=batch.project_id,
            environment=batch.environment,
            correlation_id=correlation_id,
            severity=severity,
            idempotency_key=f"telemetry:{telemetry.project}:{telemetry.timestamp.isoformat()}:{telemetry.route}",
            payload=payload,
            metadata={
                "source": "telemetry",
                "batch_source": batch.source,
            },
        )

        return envelope

    def _map_telemetry_to_event_type(self, telemetry: TelemetryPayload) -> str:
        """Map telemetry level to event type."""
        level_map = {
            "error": "ERROR_DETECTED",
            "critical": "ERROR_DETECTED",
            "warning": "ERROR_DETECTED",
            "info": "HEARTBEAT_SUCCESS",
        }
        return level_map.get(telemetry.level, "HEARTBEAT_SUCCESS")

    def _map_telemetry_to_severity(self, telemetry: TelemetryPayload) -> str:
        """Map telemetry level to severity."""
        severity_map = {
            "critical": "critical",
            "error": "high",
            "warning": "medium",
            "info": "low",
        }
        return severity_map.get(telemetry.level, "low")


# Global telemetry receiver singleton
telemetry_receiver = TelemetryReceiver()
