"""
Tests for Incident Engine

Incidents have explicit state governed by a state machine.
The UI does not own incident state — events do.
"""
import pytest

from app.database.models import IncidentStateTransition, IncidentStatus


class TestIncidentStateTransition:
    """Test the incident state machine."""

    def test_detected_to_triaging(self):
        assert IncidentStateTransition.can_transition("DETECTED", "TRIAGING")

    def test_triaging_to_investigating(self):
        assert IncidentStateTransition.can_transition("TRIAGING", "INVESTIGATING")

    def test_investigating_to_diagnosed(self):
        assert IncidentStateTransition.can_transition("INVESTIGATING", "DIAGNOSED")

    def test_diagnosed_to_awaiting_action(self):
        assert IncidentStateTransition.can_transition("DIAGNOSED", "AWAITING_ACTION")

    def test_awaiting_action_to_remediating(self):
        assert IncidentStateTransition.can_transition("AWAITING_ACTION", "REMEDIATING")

    def test_awaiting_action_to_escalated(self):
        assert IncidentStateTransition.can_transition("AWAITING_ACTION", "ESCALATED")

    def test_remediating_to_verifying(self):
        assert IncidentStateTransition.can_transition("REMEDIATING", "VERIFYING")

    def test_remediating_to_remediation_failed(self):
        assert IncidentStateTransition.can_transition("REMEDIATING", "REMEDIATION_FAILED")

    def test_verifying_to_resolved(self):
        assert IncidentStateTransition.can_transition("VERIFYING", "RESOLVED")

    def test_verifying_to_remediation_failed(self):
        assert IncidentStateTransition.can_transition("VERIFYING", "REMEDIATION_FAILED")

    def test_remediation_failed_to_escalated(self):
        assert IncidentStateTransition.can_transition("REMEDIATION_FAILED", "ESCALATED")

    def test_resolved_is_terminal(self):
        """RESOLVED is a terminal state — no transitions allowed."""
        assert IncidentStateTransition.TRANSITIONS["RESOLVED"] == []

    def test_escalated_is_terminal(self):
        """ESCALATED is a terminal state — no transitions allowed."""
        assert IncidentStateTransition.TRANSITIONS["ESCALATED"] == []

    def test_cannot_skip_from_detected_to_diagnosed(self):
        """Must go through TRIAGING and INVESTIGATING first."""
        assert not IncidentStateTransition.can_transition("DETECTED", "DIAGNOSED")

    def test_cannot_go_back_from_resolved(self):
        """Cannot transition from RESOLVED to any other state."""
        assert not IncidentStateTransition.can_transition("RESOLVED", "TRIAGING")
        assert not IncidentStateTransition.can_transition("RESOLVED", "DETECTED")

    def test_cannot_go_back_from_escalated(self):
        """Cannot transition from ESCALATED to any other state."""
        assert not IncidentStateTransition.can_transition("ESCALATED", "REMEDIATING")

    def test_invalid_transition_returns_false(self):
        """Completely invalid transitions should return False."""
        assert not IncidentStateTransition.can_transition("DETECTED", "RESOLVED")
        assert not IncidentStateTransition.can_transition("DETECTED", "REMEDIATING")

    def test_unknown_state_returns_false(self):
        """Unknown states should return False."""
        assert not IncidentStateTransition.can_transition("UNKNOWN", "TRIAGING")

    def test_investigating_can_retriage(self):
        """Investigating can go back to triaging for re-evaluation."""
        assert IncidentStateTransition.can_transition("INVESTIGATING", "TRIAGING")


class TestIncidentSeverityEscalation:
    """Test severity escalation logic."""

    def test_escalate_medium_to_high(self):
        from app.incidents.engine import IncidentEngine
        engine = IncidentEngine()
        assert engine._escalate_severity("medium") == "high"

    def test_escalate_high_to_critical(self):
        from app.incidents.engine import IncidentEngine
        engine = IncidentEngine()
        assert engine._escalate_severity("high") == "critical"

    def test_escalate_critical_stays_critical(self):
        from app.incidents.engine import IncidentEngine
        engine = IncidentEngine()
        assert engine._escalate_severity("critical") == "critical"

    def test_escalate_low_to_medium(self):
        from app.incidents.engine import IncidentEngine
        engine = IncidentEngine()
        assert engine._escalate_severity("low") == "medium"
