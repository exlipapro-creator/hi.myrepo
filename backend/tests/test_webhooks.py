"""
Tests for webhook ingestion endpoints.

Tests:
- Replay protection
- GitHub signature verification
- Custom webhook signature verification
- Event mapping
"""
import hashlib
import hmac
import time
from unittest.mock import patch

import pytest

from app.api.webhooks import (
    _check_replay,
    _determine_github_severity,
    _map_github_event,
    _seen_webhook_ids,
    _verify_github_signature,
)


class TestReplayProtection:
    """Test webhook replay protection."""

    def setup_method(self):
        """Clear seen IDs before each test."""
        _seen_webhook_ids.clear()

    def test_first_delivery_accepted(self):
        assert _check_replay("delivery-123") is False

    def test_duplicate_delivery_rejected(self):
        _check_replay("delivery-456")
        assert _check_replay("delivery-456") is True

    def test_different_deliveries_accepted(self):
        _check_replay("delivery-001")
        assert _check_replay("delivery-002") is False

    def test_expired_entries_cleaned(self):
        # Simulate an old entry
        _seen_webhook_ids["old-delivery"] = time.time() - 400  # 6+ minutes ago
        _check_replay("new-delivery")
        assert "old-delivery" not in _seen_webhook_ids
        assert "new-delivery" in _seen_webhook_ids


class TestGitHubSignature:
    """Test GitHub webhook HMAC signature verification."""

    def test_valid_signature(self):
        secret = "my-secret-key"
        payload = b'{"action": "push"}'
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert _verify_github_signature(payload, expected, secret) is True

    def test_invalid_signature(self):
        assert _verify_github_signature(
            b'{"action": "push"}',
            "sha256=invalidhash",
            "my-secret-key",
        ) is False

    def test_empty_secret_returns_false(self):
        assert _verify_github_signature(b'payload', "sha256=abc", "") is False

    def test_tampered_payload(self):
        secret = "my-secret-key"
        payload = b'{"action": "push"}'
        signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        tampered = b'{"action": "delete"}'
        assert _verify_github_signature(tampered, signature, secret) is False


class TestGitHubEventMapping:
    """Test GitHub event to internal event type mapping."""

    def test_push_to_deployment_started(self):
        assert _map_github_event("push", "") == "DEPLOYMENT_STARTED"

    def test_deployment_success(self):
        assert _map_github_event("deployment_status", "success") == "DEPLOYMENT_SUCCEEDED"

    def test_deployment_failure(self):
        assert _map_github_event("deployment_status", "failure") == "DEPLOYMENT_FAILED"

    def test_workflow_run_completed(self):
        assert _map_github_event("workflow_run", "completed") == "DEPLOYMENT_SUCCEEDED"

    def test_workflow_run_failure(self):
        assert _map_github_event("workflow_run", "failure") == "DEPLOYMENT_FAILED"

    def test_unknown_event_maps_to_heartbeat(self):
        assert _map_github_event("unknown_event", "unknown") == "HEARTBEAT_SUCCESS"


class TestGitHubSeverity:
    """Test GitHub severity determination."""

    def test_failure_is_high(self):
        assert _determine_github_severity("push", "failure") == "high"

    def test_error_is_high(self):
        assert _determine_github_severity("issues", "error") == "high"

    def test_deployment_failure_is_high(self):
        assert _determine_github_severity("deployment_status", "failure") == "high"

    def test_success_is_low(self):
        assert _determine_github_severity("push", "success") == "low"

    def test_default_is_low(self):
        assert _determine_github_severity("unknown", "unknown") == "low"
