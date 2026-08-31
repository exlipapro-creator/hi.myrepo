"""
Tests for Error Fingerprinting Engine

The fingerprinting engine normalizes errors to prevent alert storms.
182 identical errors → 1 error group → 1 incident.
"""
import pytest

from app.events.fingerprinting import ErrorInput, FingerprintEngine, FingerprintResult


class TestFingerprintEngine:
    """Test the deterministic fingerprinting engine."""

    def setup_method(self):
        self.engine = FingerprintEngine()

    def test_same_error_produces_same_fingerprint(self):
        """Identical errors must always produce the same fingerprint."""
        error = ErrorInput(
            error_type="TypeError",
            error_message="Cannot read property 'id' of undefined",
            route="/api/checkout",
        )
        result1 = self.engine.fingerprint(error)
        result2 = self.engine.fingerprint(error)
        assert result1.fingerprint == result2.fingerprint

    def test_different_errors_produce_different_fingerprints(self):
        """Different errors should produce different fingerprints."""
        error1 = ErrorInput(
            error_type="TypeError",
            error_message="Cannot read property 'id' of undefined",
        )
        error2 = ErrorInput(
            error_type="ReferenceError",
            error_message="foo is not defined",
        )
        result1 = self.engine.fingerprint(error1)
        result2 = self.engine.fingerprint(error2)
        assert result1.fingerprint != result2.fingerprint

    def test_message_normalization_removes_ids(self):
        """UUIDs and long numeric IDs should be normalized."""
        error1 = ErrorInput(
            error_type="DatabaseError",
            error_message="Record 12345678 not found",
        )
        error2 = ErrorInput(
            error_type="DatabaseError",
            error_message="Record 99999999 not found",
        )
        result1 = self.engine.fingerprint(error1)
        result2 = self.engine.fingerprint(error2)
        # Same fingerprint because 8-digit IDs are normalized to <ID>
        assert result1.fingerprint == result2.fingerprint

    def test_route_affects_fingerprint(self):
        """Same error on different routes should have different fingerprints."""
        error1 = ErrorInput(
            error_type="HTTPError",
            error_message="Service unavailable",
            route="/api/checkout",
        )
        error2 = ErrorInput(
            error_type="HTTPError",
            error_message="Service unavailable",
            route="/api/inventory",
        )
        result1 = self.engine.fingerprint(error1)
        result2 = self.engine.fingerprint(error2)
        assert result1.fingerprint != result2.fingerprint

    def test_fingerprint_is_deterministic_hash(self):
        """Fingerprint should be a 16-char hex string."""
        error = ErrorInput(
            error_type="Error",
            error_message="Something went wrong",
        )
        result = self.engine.fingerprint(error)
        assert len(result.fingerprint) == 16
        assert all(c in "0123456789abcdef" for c in result.fingerprint)

    def test_stack_normalization(self):
        """Stack traces should be normalized to remove line numbers."""
        stack = (
            "at processTicksAndRejections (node:internal/process/task_queues:95:5)\n"
            "at async /app/src/services/checkout.js:142:15\n"
            "at async /app/src/routes/api.js:45:8"
        )
        error = ErrorInput(
            error_type="TypeError",
            error_message="Cannot read properties of null",
            stack_trace=stack,
        )
        result = self.engine.fingerprint(error)
        # Stack should be normalized
        assert result.normalized_stack is not None
        assert len(result.normalized_stack) > 0

    def test_normalized_message_preserves_structure(self):
        """Normalization should keep the error type and structure."""
        error = ErrorInput(
            error_type="ValueError",
            error_message="Invalid input for field name",
        )
        result = self.engine.fingerprint(error)
        assert "invalid input for field name" in result.normalized_message

    def test_empty_route_handled(self):
        """Errors without routes should still fingerprint correctly."""
        error = ErrorInput(
            error_type="RuntimeError",
            error_message="Unexpected condition",
        )
        result = self.engine.fingerprint(error)
        assert result.fingerprint is not None
        assert result.route is None

    def test_email_normalization(self):
        """Email addresses should be normalized."""
        error1 = ErrorInput(
            error_type="AuthError",
            error_message="User john@example.com not authorized",
        )
        error2 = ErrorInput(
            error_type="AuthError",
            error_message="User jane@test.org not authorized",
        )
        result1 = self.engine.fingerprint(error1)
        result2 = self.engine.fingerprint(error2)
        # Same fingerprint because emails are normalized
        assert result1.fingerprint == result2.fingerprint
