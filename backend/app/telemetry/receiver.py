"""
hi.myrepo - Telemetry Receiver

Zero-SDK telemetry using navigator.sendBeacon().
Captures useful operational information with a sanitization boundary.

Must NOT capture: passwords, tokens, payment credentials, secrets, PII.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.events.spine import EventEnvelope, event_processor


class TelemetryPayload(BaseModel):
    """
    Client telemetry payload.
    Sent via navigator.sendBeacon() from the frontend.
    """
    route: str = ""
    timestamp: datetime
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    browser_info: Optional[str] = None
    runtime: Optional[str] = None  # browser, node, edge
    release: Optional[str] = None
    version: Optional[str] = None
    project: str = ""
    environment: str = "production"
    correlation_id: Optional[str] = None
    level: str = "info"  # info, warning, error, critical
    message: str = ""
    metadata: dict = Field(default_factory=dict)

    @field_validator("error_message", "stack_trace", "message")
    @classmethod
    def sanitize_field(cls, v: Optional[str]) -> Optional[str]:
        """Remove potentially sensitive information."""
        if v is None:
            return v
        # Remove common secret patterns
        import re
        sanitized = v
        # Remove API keys
        sanitized = re.sub(r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+", "[REDACTED]", sanitized, flags=re.IGNORECASE)
        # Remove bearer tokens
        sanitized = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", sanitized)
        # Remove basic auth
        sanitized = re.sub(r"Basic\s+\S+", "Basic [REDACTED]", sanitized)
        return sanitized


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
    """

    # Maximum payload size to prevent abuse
    MAX_BATCH_SIZE = 50
    MAX_EVENT_SIZE = 10_000  # characters

    async def receive_batch(self, batch: TelemetryBatch, session=None) -> dict:
        """
        Process a batch of telemetry events.
        If a session is provided, events are persisted to the event spine.
        Returns a summary of processed events.
        """
        processed = 0
        errors = 0

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
        """Process a single telemetry event."""
        # Determine event type
        event_type = self._map_telemetry_to_event_type(telemetry)
        severity = self._map_telemetry_to_severity(telemetry)

        # Create event envelope
        correlation_id = None
        if telemetry.correlation_id:
            try:
                correlation_id = uuid.UUID(telemetry.correlation_id)
            except ValueError:
                pass

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
            payload={
                "route": telemetry.route,
                "error_message": telemetry.error_message,
                "stack_trace": telemetry.stack_trace,
                "browser_info": telemetry.browser_info,
                "runtime": telemetry.runtime,
                "release": telemetry.release,
                "version": telemetry.version,
                "level": telemetry.level,
                "message": telemetry.message,
            },
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
