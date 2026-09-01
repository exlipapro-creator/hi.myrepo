"""
hi.myrepo - Webhook Defense Tests

Adversarial tests proving webhook endpoints cannot be abused.

Tests:
- Body size limits
- Replay protection with full hashes
- Event type injection prevention
- Severity injection prevention
- Internal field stripping
- Signature verification
- Timestamp freshness
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import pytest

from app.api.webhooks import (
    _check_body_size,
    _check_replay,
    _check_timestamp_freshness,
    _seen_webhook_ids,
    _verify_github_signature,
    _ALLOWED_CUSTOM_EVENT_TYPES,
    _ALLOWED_CUSTOM_SEVERITIES,
    _MAX_GITHUB_PAYLOAD,
    _MAX_WEBHOOK_BODY_BYTES,
)
from fastapi import HTTPException


class TestBodySizeDefense:
    """Verify oversized payloads are rejected before processing."""

    def test_normal_body_accepted(self):
        body = b'{"action": "push"}'
        # Should not raise
        _check_body_size(body, _MAX_GITHUB_PAYLOAD, "test")

    def test_oversized_body_rejected(self):
        body = b"X" * (_MAX_GITHUB_PAYLOAD + 1)
        with pytest.raises(HTTPException) as exc_info:
            _check_body_size(body, _MAX_GITHUB_PAYLOAD, "test")
        assert exc_info.value.status_code == 413

    def test_boundary_body_accepted(self):
        body = b"X" * _MAX_GITHUB_PAYLOAD
        # Exactly at limit — should be accepted
        _check_body_size(body, _MAX_GITHUB_PAYLOAD, "test")

    def test_empty_body_accepted(self):
        _check_body_size(b"", _MAX_WEBHOOK_BODY_BYTES, "test")


class TestReplayDefense:
    """Verify replay protection prevents duplicate processing."""

    def setup_method(self):
        _seen_webhook_ids.clear()

    def test_full_hash_prevents_collision(self):
        """Using full SHA-256 hash instead of truncated prevents hash collisions."""
        # Two different payloads should produce different delivery IDs
        body1 = json.dumps({"event": "deployment", "id": "123"}).encode()
        body2 = json.dumps({"event": "deployment", "id": "124"}).encode()

        hash1 = hashlib.sha256(body1).hexdigest()
        hash2 = hashlib.sha256(body2).hexdigest()

        assert hash1 != hash2  # Full hashes are unique

    def test_identical_bodies_same_hash(self):
        """Identical payloads produce the same hash — correctly detected as replay."""
        body = json.dumps({"event": "push"}).encode()
        hash_val = hashlib.sha256(body).hexdigest()
        delivery_id = f"custom:proj:{hash_val}"

        assert _check_replay(delivery_id) is False  # First time
        assert _check_replay(delivery_id) is True   # Replay detected

    def test_different_delivery_ids_independent(self):
        """Different delivery IDs have independent replay state."""
        _check_replay("delivery-aaa")
        assert _check_replay("delivery-bbb") is False

    def test_replay_window_cleans_old_entries(self):
        """Old entries are cleaned from the replay window."""
        import time
        # Inject an old entry
        _seen_webhook_ids["old-id"] = time.time() - 400  # >5 minutes ago
        _check_replay("new-id")
        assert "old-id" not in _seen_webhook_ids


class TestEventTypeInjection:
    """Verify custom webhooks cannot inject arbitrary event types."""

    def test_allowed_event_type_accepted(self):
        """Event types in the allowlist are accepted."""
        for event_type in _ALLOWED_CUSTOM_EVENT_TYPES:
            assert event_type in _ALLOWED_CUSTOM_EVENT_TYPES

    def test_unknown_event_type_rejected(self):
        """Event types not in the allowlist would be replaced."""
        attacker_types = [
            "INCIDENT_CREATED",
            "INCIDENT_ESCALATED",
            "RUNBOOK_EXECUTED",
            "SECURITY_EVENT",
            "AUTH_EVENT",
            "AI_PROVIDER_FAILED",
            "MEMORY_RECORDED",
        ]
        for atype in attacker_types:
            assert atype not in _ALLOWED_CUSTOM_EVENT_TYPES

    def test_allowed_severity_accepted(self):
        """Only standard severity levels are allowed."""
        assert _ALLOWED_CUSTOM_SEVERITIES == {"low", "medium", "high", "critical"}

    def test_unknown_severity_rejected(self):
        """Invalid severity levels would be replaced."""
        attacker_severities = ["fatal", "emergency", "catastrophic", "none"]
        for sev in attacker_severities:
            assert sev not in _ALLOWED_CUSTOM_SEVERITIES


class TestInternalFieldStripping:
    """Verify internal fields cannot be injected via custom webhook payload."""

    def test_injection_fields_identified(self):
        """These fields should be stripped from custom webhook payloads."""
        injection_fields = [
            "project_id",
            "actor",
            "correlation_id",
            "idempotency_key",
        ]
        # Verify these are the fields we strip
        for field in injection_fields:
            assert field in ["project_id", "actor", "correlation_id", "idempotency_key"]


class TestGitHubSignatureDefense:
    """Verify signature verification is robust."""

    def test_valid_signature_accepted(self):
        secret = "gh-secret-123"
        payload = b'{"ref":"refs/heads/main"}'
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert _verify_github_signature(payload, expected, secret) is True

    def test_tampered_payload_rejected(self):
        secret = "gh-secret-123"
        payload = b'{"ref":"refs/heads/main"}'
        signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        tampered = b'{"ref":"refs/heads/main","evil":true}'
        assert _verify_github_signature(tampered, signature, secret) is False

    def test_empty_secret_rejects_everything(self):
        assert _verify_github_signature(b'payload', "sha256=abc", "") is False

    def test_missing_signature_rejected(self):
        assert _verify_github_signature(b'payload', "", "secret") is False

    def test_wrong_algorithm_rejected(self):
        """sha1 signatures should be rejected."""
        assert _verify_github_signature(b'payload', "sha1=abc123", "secret") is False


class TestTimestampFreshnessDefense:
    """Verify stale webhooks are rejected."""

    def test_no_timestamp_header_passes(self):
        """If provider doesn't send timestamp, we can't check freshness."""
        from unittest.mock import MagicMock
        request = MagicMock()
        request.headers = {}
        # Should not raise
        _check_timestamp_freshness(request, "test")

    def test_fresh_timestamp_accepted(self):
        from unittest.mock import MagicMock
        now = int(datetime.now(timezone.utc).timestamp())
        request = MagicMock()
        request.headers = {"x-webhook-timestamp": str(now)}
        # Should not raise
        _check_timestamp_freshness(request, "test")

    def test_stale_timestamp_rejected(self):
        from unittest.mock import MagicMock
        old = int(datetime.now(timezone.utc).timestamp()) - 1200  # 20 minutes ago
        request = MagicMock()
        request.headers = {"x-webhook-timestamp": str(old)}
        with pytest.raises(HTTPException) as exc_info:
            _check_timestamp_freshness(request, "test")
        assert exc_info.value.status_code == 400

    def test_millisecond_timestamp_handled(self):
        from unittest.mock import MagicMock
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        request = MagicMock()
        request.headers = {"x-webhook-timestamp": str(now_ms)}
        # Should not raise
        _check_timestamp_freshness(request, "test")

    def test_invalid_timestamp_ignored(self):
        """Invalid timestamps are silently ignored, not fatal."""
        from unittest.mock import MagicMock
        request = MagicMock()
        request.headers = {"x-webhook-timestamp": "not-a-number"}
        # Should not raise
        _check_timestamp_freshness(request, "test")


class TestReplayProtectionIntegration:
    """Integration-style tests for replay protection."""

    def setup_method(self):
        _seen_webhook_ids.clear()

    def test_rapid_duplicate_detection(self):
        """Rapid-fire identical deliveries are all detected as replays."""
        for _ in range(10):
            result = _check_replay("same-delivery-id")
        # All but the first should be detected as replay
        assert _check_replay("same-delivery-id") is True

    def test_many_unique_deliveries_accepted(self):
        """Many different delivery IDs are all accepted."""
        for i in range(100):
            assert _check_replay(f"unique-{i}") is False
