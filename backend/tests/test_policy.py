"""
Tests for Policy Engine

The policy engine is the actual authority layer.
Deterministic — no AI, no randomness, pure rule evaluation.
"""
import pytest

from app.policy.engine import PolicyContext, PolicyDecision, PolicyEngine


class TestPolicyEngine:
    """Test deterministic policy evaluation."""

    def setup_method(self):
        self.engine = PolicyEngine()

    def test_default_requires_approval(self):
        """With no policies, default to requiring approval."""
        import asyncio
        from sqlalchemy.ext.asyncio import AsyncSession

        async def _test():
            from unittest.mock import AsyncMock, MagicMock

            mock_session = AsyncMock()
            # Return no policies
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            context = PolicyContext(
                confidence=0.95,
                blast_radius="low",
                autonomy_level=4,
            )
            evaluation = await self.engine.evaluate(context, "runbook", mock_session)
            assert evaluation.decision == PolicyDecision.REQUIRE_APPROVAL
            assert "No policies configured" in evaluation.reason

        asyncio.run(_test())

    def test_condition_comparison_gte(self):
        """Test greater-than-or-equal comparison."""
        assert self.engine._compare(0.95, "gte", 0.90) is True
        assert self.engine._compare(0.85, "gte", 0.90) is False

    def test_condition_comparison_lte(self):
        """Test less-than-or-equal comparison."""
        assert self.engine._compare(0.30, "lte", 0.50) is True
        assert self.engine._compare(0.70, "lte", 0.50) is False

    def test_condition_comparison_in(self):
        """Test 'in' comparison."""
        assert self.engine._compare("low", "in", ["low", "medium"]) is True
        assert self.engine._compare("critical", "in", ["low", "medium"]) is False

    def test_condition_comparison_eq(self):
        """Test equality comparison."""
        assert self.engine._compare("allow", "eq", "allow") is True
        assert self.engine._compare("deny", "eq", "allow") is False

    def test_condition_comparison_neq(self):
        """Test not-equal comparison."""
        assert self.engine._compare("deny", "neq", "allow") is True
        assert self.engine._compare("allow", "neq", "allow") is False

    def test_condition_comparison_gt(self):
        """Test greater-than comparison."""
        assert self.engine._compare(0.95, "gt", 0.90) is True
        assert self.engine._compare(0.90, "gt", 0.90) is False

    def test_condition_comparison_lt(self):
        """Test less-than comparison."""
        assert self.engine._compare(0.30, "lt", 0.50) is True
        assert self.engine._compare(0.50, "lt", 0.50) is False

    def test_condition_comparison_contains(self):
        """Test contains comparison."""
        assert self.engine._compare("high confidence result", "contains", "high") is True
        assert self.engine._compare("low confidence", "contains", "critical") is False

    def test_condition_value_none_returns_false(self):
        """None values should always return False."""
        assert self.engine._check_condition(None, "confidence", 0.90) is False

    def test_get_condition_value_from_incident(self):
        """Values should be extracted from incident context."""
        context = PolicyContext(
            incident={"confidence": 0.95, "blast_radius": "low"},
        )
        assert self.engine._get_condition_value("confidence", context) == 0.95
        assert self.engine._get_condition_value("blast_radius", context) == "low"

    def test_get_condition_value_from_direct_context(self):
        """Direct context fields should be returned."""
        context = PolicyContext(autonomy_level=4)
        assert self.engine._get_condition_value("autonomy_level", context) == 4

    def test_bool_condition(self):
        """Boolean conditions should be checked directly."""
        assert self.engine._check_condition(True, "reversible", True) is True
        assert self.engine._check_condition(False, "reversible", True) is False
