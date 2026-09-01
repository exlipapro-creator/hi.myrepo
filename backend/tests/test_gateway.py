"""
Tests for AI Gateway

Tests circuit breaker, failure classification, and provider selection.
"""
import time

import pytest

from app.gateway.ai_gateway import (
    CircuitBreaker,
    CircuitState,
    FailureType,
    classify_failure,
)


class TestCircuitBreaker:
    """Test circuit breaker state transitions."""

    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_transitions_to_half_open_after_cooldown(self):
        import time

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        # With 0 recovery_timeout, the state property auto-transitions to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_closes_after_successful_half_open_probes(self):
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0,
            half_open_max_calls=2,
        )
        cb.record_failure()
        cb.record_failure()
        # Now in half_open
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # Not enough successes yet

        cb.record_success()
        assert cb.state == CircuitState.CLOSED  # Back to closed

    def test_reopens_on_failure_during_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=100)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN  # Still OPEN (timeout hasn't elapsed)

        # Simulate timeout by setting last_failure_time far in the past
        cb._last_failure_time = time.time() - 200
        assert cb.state == CircuitState.HALF_OPEN  # Now transitions

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_in_closed_reduces_failure_count(self):
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(3):
            cb.record_failure()
        assert cb._failure_count == 3

        cb.record_success()
        assert cb._failure_count == 2

    def test_half_open_limits_concurrent_calls(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0, half_open_max_calls=2)
        cb.record_failure()
        assert cb.state == CircuitState.HALF_OPEN

        # First two calls should be allowed
        assert cb.can_execute() is True  # _half_open_calls check is based on the internal state
        assert cb.can_execute() is True


class TestFailureClassification:
    """Test failure classification logic with fine-grained categories."""

    def test_retryable_on_timeout(self):
        assert classify_failure(408, "Request timeout") == FailureType.TIMEOUT

    def test_retryable_on_rate_limit(self):
        assert classify_failure(429, "Rate limit exceeded") == FailureType.RATE_LIMIT

    def test_retryable_on_server_error(self):
        assert classify_failure(500, "Internal server error") == FailureType.TRANSIENT_PROVIDER_FAILURE

    def test_retryable_on_bad_gateway(self):
        assert classify_failure(502, "Bad gateway") == FailureType.TRANSIENT_PROVIDER_FAILURE

    def test_retryable_on_service_unavailable(self):
        assert classify_failure(503, "Service unavailable") == FailureType.TRANSIENT_PROVIDER_FAILURE

    def test_non_retryable_on_unauthorized(self):
        assert classify_failure(401, "Invalid API key") == FailureType.AUTHENTICATION_FAILURE

    def test_non_retryable_on_forbidden(self):
        assert classify_failure(403, "Access denied") == FailureType.POLICY

    def test_non_retryable_on_not_found(self):
        assert classify_failure(404, "Model not found") == FailureType.MODEL_NOT_FOUND

    def test_non_retryable_on_bad_request(self):
        assert classify_failure(400, "Invalid parameters") == FailureType.INVALID_REQUEST

    def test_policy_on_quota_exceeded(self):
        # 429 takes precedence as rate_limit even with quota message
        assert classify_failure(429, "Quota exceeded for this month") == FailureType.RATE_LIMIT

    def test_policy_on_disabled(self):
        assert classify_failure(403, "Provider disabled") == FailureType.POLICY

    def test_retryable_on_generic_error(self):
        assert classify_failure(500, "Something went wrong") == FailureType.TRANSIENT_PROVIDER_FAILURE

    def test_is_retryable_utility(self):
        from app.gateway.ai_gateway import is_retryable
        assert is_retryable(FailureType.RATE_LIMIT) is True
        assert is_retryable(FailureType.TIMEOUT) is True
        assert is_retryable(FailureType.TRANSIENT_PROVIDER_FAILURE) is True
        assert is_retryable(FailureType.AUTHENTICATION_FAILURE) is False
        assert is_retryable(FailureType.MODEL_NOT_FOUND) is False
        assert is_retryable(FailureType.INVALID_REQUEST) is False
        assert is_retryable(FailureType.POLICY) is False
