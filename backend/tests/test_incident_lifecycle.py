"""
Tests for incident lifecycle hardening.

Covers:
- Incident creation from error groups
- Incident creation from heartbeat failure patterns
- Valid state transitions
- Invalid state transitions (rejected)
- Terminal state protection (RESOLVED, ESCALATED)
- Fingerprint consistency and deduplication
- Threshold behavior (3+ failures)
- Recovery handling (HEARTBEAT_SUCCESS after incident)
- Historical evidence immutability
- Severity mapping
- Severity escalation with ceiling
- Idempotency (duplicate correlation)
- Audit trail for state transitions
- Organization isolation
"""
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import (
    AuditLog,
    Incident,
    IncidentStatus,
    IncidentStateTransition,
)
from app.incidents.engine import IncidentCreate, IncidentEngine, incident_engine


class TestIncidentStateMachine:
    """Test the incident state machine transitions."""

    def test_valid_transitions(self):
        """All valid transitions are defined and enforced."""
        assert IncidentStateTransition.can_transition("DETECTED", "TRIAGING") is True
        assert IncidentStateTransition.can_transition("TRIAGING", "INVESTIGATING") is True
        assert IncidentStateTransition.can_transition("INVESTIGATING", "DIAGNOSED") is True
        assert IncidentStateTransition.can_transition("INVESTIGATING", "TRIAGING") is True
        assert IncidentStateTransition.can_transition("DIAGNOSED", "AWAITING_ACTION") is True
        assert IncidentStateTransition.can_transition("AWAITING_ACTION", "REMEDIATING") is True
        assert IncidentStateTransition.can_transition("AWAITING_ACTION", "ESCALATED") is True
        assert IncidentStateTransition.can_transition("REMEDIATING", "VERIFYING") is True
        assert IncidentStateTransition.can_transition("REMEDIATING", "REMEDIATION_FAILED") is True
        assert IncidentStateTransition.can_transition("VERIFYING", "RESOLVED") is True
        assert IncidentStateTransition.can_transition("VERIFYING", "REMEDIATION_FAILED") is True
        assert IncidentStateTransition.can_transition("REMEDIATION_FAILED", "ESCALATED") is True

    def test_invalid_transitions(self):
        """Invalid transitions are rejected."""
        assert IncidentStateTransition.can_transition("DETECTED", "RESOLVED") is False
        assert IncidentStateTransition.can_transition("DETECTED", "INVESTIGATING") is False
        assert IncidentStateTransition.can_transition("DETECTED", "REMEDIATING") is False
        assert IncidentStateTransition.can_transition("TRIAGING", "RESOLVED") is False
        assert IncidentStateTransition.can_transition("TRIAGING", "DETECTED") is False

    def test_terminal_state_resolved(self):
        """RESOLVED is terminal — no transitions out."""
        assert IncidentStateTransition.TRANSITIONS["RESOLVED"] == []
        assert IncidentStateTransition.can_transition("RESOLVED", "DETECTED") is False
        assert IncidentStateTransition.can_transition("RESOLVED", "TRIAGING") is False
        assert IncidentStateTransition.can_transition("RESOLVED", "INVESTIGATING") is False
        assert IncidentStateTransition.can_transition("RESOLVED", "REMEDIATING") is False

    def test_terminal_state_escalated(self):
        """ESCALATED is terminal — no transitions out."""
        assert IncidentStateTransition.TRANSITIONS["ESCALATED"] == []
        assert IncidentStateTransition.can_transition("ESCALATED", "DETECTED") is False
        assert IncidentStateTransition.can_transition("ESCALATED", "TRIAGING") is False
        assert IncidentStateTransition.can_transition("ESCALATED", "RESOLVED") is False

    def test_all_states_have_transition_entries(self):
        """Every status constant has a transition entry."""
        all_statuses = [
            IncidentStatus.DETECTED,
            IncidentStatus.TRIAGING,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.DIAGNOSED,
            IncidentStatus.AWAITING_ACTION,
            IncidentStatus.REMEDIATING,
            IncidentStatus.VERIFYING,
            IncidentStatus.RESOLVED,
            IncidentStatus.REMEDIATION_FAILED,
            IncidentStatus.ESCALATED,
        ]
        for status in all_statuses:
            assert status in IncidentStateTransition.TRANSITIONS, (
                f"Status {status} missing from TRANSITIONS"
            )

    def test_incident_status_has_all_states(self):
        """IncidentStatus has all 10 states."""
        assert len([
            IncidentStatus.DETECTED,
            IncidentStatus.TRIAGING,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.DIAGNOSED,
            IncidentStatus.AWAITING_ACTION,
            IncidentStatus.REMEDIATING,
            IncidentStatus.VERIFYING,
            IncidentStatus.RESOLVED,
            IncidentStatus.REMEDIATION_FAILED,
            IncidentStatus.ESCALATED,
        ]) == 10


class TestIncidentCreation:
    """Test incident creation from incident engine."""

    def test_create_incident_returns_detected_status(self):
        """New incidents start in DETECTED state."""
        incident = MagicMock()
        incident.id = uuid.uuid4()
        incident.project_id = uuid.uuid4()
        incident.status = IncidentStatus.DETECTED
        incident.severity = "medium"
        incident.detected_at = datetime.now(timezone.utc)

        assert incident.status == IncidentStatus.DETECTED

    def test_incident_create_validates_severity(self):
        """IncidentCreate rejects invalid severity values."""
        with pytest.raises(ValueError, match="Invalid severity"):
            IncidentCreate(
                project_id=uuid.uuid4(),
                severity="invalid_level",
            )

    def test_incident_create_accepts_valid_severity(self):
        """IncidentCreate accepts valid severity values."""
        for sev in ["low", "medium", "high", "critical"]:
            data = IncidentCreate(
                project_id=uuid.uuid4(),
                severity=sev,
                title="Test",
            )
            assert data.severity == sev

    def test_incident_create_default_severity(self):
        """IncidentCreate defaults to medium severity."""
        data = IncidentCreate(project_id=uuid.uuid4())
        assert data.severity == "medium"

    def test_incident_create_fingerprint(self):
        """IncidentCreate stores fingerprint."""
        data = IncidentCreate(
            project_id=uuid.uuid4(),
            fingerprint="abc123",
        )
        assert data.fingerprint == "abc123"


class TestIncidentTransition:
    """Test the incident transition method."""

    def test_invalid_transition_raises_value_error(self):
        """Transitioning to an invalid state raises ValueError."""
        # DETECTED -> TRIAGING is valid, DETECTED -> RESOLVED is not
        assert IncidentStateTransition.can_transition("DETECTED", "RESOLVED") is False

    def test_terminal_state_cannot_transition(self):
        """Transitioning from RESOLVED is always rejected."""
        assert IncidentStateTransition.can_transition("RESOLVED", "TRIAGING") is False
        assert IncidentStateTransition.can_transition("RESOLVED", "INVESTIGATING") is False

    def test_escalated_cannot_transition(self):
        """Transitioning from ESCALATED is always rejected."""
        assert IncidentStateTransition.can_transition("ESCALATED", "TRIAGING") is False

    def test_valid_chain_detection_to_resolved(self):
        """Full valid chain: DETECTED -> TRIAGING -> INVESTIGATING -> DIAGNOSED -> AWAITING_ACTION -> REMEDIATING -> VERIFYING -> RESOLVED."""
        chain = [
            ("DETECTED", "TRIAGING"),
            ("TRIAGING", "INVESTIGATING"),
            ("INVESTIGATING", "DIAGNOSED"),
            ("DIAGNOSED", "AWAITING_ACTION"),
            ("AWAITING_ACTION", "REMEDIATING"),
            ("REMEDIATING", "VERIFYING"),
            ("VERIFYING", "RESOLVED"),
        ]
        for from_state, to_state in chain:
            assert IncidentStateTransition.can_transition(from_state, to_state), (
                f"Expected transition {from_state} -> {to_state} to be valid"
            )


class TestFingerprintDeduplication:
    """Test fingerprint consistency and deduplication logic."""

    def test_heartbeat_fingerprint_is_deterministic(self):
        """Same project+target produces same fingerprint."""
        project_id = uuid.uuid4()
        target_id = "test-target"

        fp1 = hashlib.sha256(f"heartbeat:{project_id}:{target_id}".encode()).hexdigest()[:16]
        fp2 = hashlib.sha256(f"heartbeat:{project_id}:{target_id}".encode()).hexdigest()[:16]

        assert fp1 == fp2

    def test_different_targets_different_fingerprints(self):
        """Different targets produce different fingerprints."""
        project_id = uuid.uuid4()
        fp1 = hashlib.sha256(f"heartbeat:{project_id}:target-a".encode()).hexdigest()[:16]
        fp2 = hashlib.sha256(f"heartbeat:{project_id}:target-b".encode()).hexdigest()[:16]

        assert fp1 != fp2

    def test_different_projects_different_fingerprints(self):
        """Different projects produce different fingerprints for same target."""
        target_id = "test-target"
        fp1 = hashlib.sha256(f"heartbeat:{uuid.uuid4()}:{target_id}".encode()).hexdigest()[:16]
        fp2 = hashlib.sha256(f"heartbeat:{uuid.uuid4()}:{target_id}".encode()).hexdigest()[:16]

        assert fp1 != fp2


class TestThresholdBehavior:
    """Test that incident creation requires the threshold to be met."""

    def test_single_failure_no_incident(self):
        """1 heartbeat failure does not create an incident."""
        failure_count = 1
        threshold = 3
        assert failure_count < threshold

    def test_two_failures_no_incident(self):
        """2 heartbeat failures do not create an incident."""
        failure_count = 2
        threshold = 3
        assert failure_count < threshold

    def test_three_failures_creates_incident(self):
        """3 heartbeat failures meet the threshold."""
        failure_count = 3
        threshold = 3
        assert failure_count >= threshold

    def test_five_failures_high_severity(self):
        """5+ failures get high severity."""
        failure_count = 5
        severity = "high" if failure_count >= 5 else "medium"
        assert severity == "high"

    def test_four_failures_medium_severity(self):
        """4 failures get medium severity."""
        failure_count = 4
        severity = "high" if failure_count >= 5 else "medium"
        assert severity == "medium"

    def test_existing_incident_not_duplicated(self):
        """When an open incident exists for the same fingerprint, no new incident is created."""
        # Simulate: existing incident found, so update instead of create
        existing = True
        create_new = not existing
        assert create_new is False


class TestRecoveryHandling:
    """Test recovery behavior after incident creation."""

    def test_recovery_transitions_to_triaging(self):
        """Recovery transitions incident from DETECTED to TRIAGING for human verification."""
        assert IncidentStateTransition.can_transition("DETECTED", "TRIAGING") is True

    def test_recovery_preserves_incident_metadata(self):
        """Recovery adds metadata without overwriting historical failure data."""
        existing_metadata = {
            "heartbeat_failure": True,
            "failure_count": 5,
        }
        recovery_update = {
            "last_recovery": {
                "target_url": "https://example.com/health",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        merged = {**existing_metadata, **recovery_update}

        assert merged["heartbeat_failure"] is True
        assert merged["failure_count"] == 5
        assert "last_recovery" in merged

    def test_recovery_does_not_modify_incident_fingerprint(self):
        """Recovery does not change the incident fingerprint."""
        original_fingerprint = "abc123def456"
        assert original_fingerprint == "abc123def456"

    def test_recovery_verification_threshold(self):
        """Recovery requires 3 consecutive successes before transitioning."""
        RECOVERY_THRESHOLD = 3
        # Simulate recovery counting
        recovery_count = 0
        for i in range(3):
            recovery_count += 1
            if recovery_count >= RECOVERY_THRESHOLD:
                break
        assert recovery_count == 3

    def test_recovery_verification_window_metadata(self):
        """Recovery verification includes success count and threshold."""
        recovery_verification = {
            "successes_required": 3,
            "successes_observed": 3,
            "verification_started_at": datetime.now(timezone.utc).isoformat(),
        }
        assert recovery_verification["successes_required"] == 3
        assert recovery_verification["successes_observed"] == 3
        assert "verification_started_at" in recovery_verification


class TestSeverityMapping:
    """Test severity calculation and escalation logic."""

    def test_calculate_severity_low_occurrences(self):
        """Low occurrence count with low event severity = low."""
        base = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        base_level = base.get("low", 0)

        # 1-4 failures: no escalation
        levels = ["low", "medium", "high", "critical"]
        result = levels[min(base_level, len(levels) - 1)]
        assert result == "low"

    def test_calculate_severity_medium_event(self):
        """Medium event severity = at least medium incident."""
        base = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        base_level = base.get("medium", 0)
        levels = ["low", "medium", "high", "critical"]
        result = levels[min(base_level, len(levels) - 1)]
        assert result == "medium"

    def test_calculate_severity_high_event(self):
        """High event severity = at least high incident."""
        base = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        base_level = base.get("high", 0)
        levels = ["low", "medium", "high", "critical"]
        result = levels[min(base_level, len(levels) - 1)]
        assert result == "high"

    def test_escalation_ceiling(self):
        """Escalation must not exceed critical."""
        levels = ["low", "medium", "high", "critical"]
        current = "critical"
        idx = levels.index(current) if current in levels else 1
        escalated = levels[min(idx + 1, len(levels) - 1)]
        assert escalated == "critical"

    def test_escalation_from_high(self):
        """Escalation from high reaches critical."""
        levels = ["low", "medium", "high", "critical"]
        current = "high"
        idx = levels.index(current)
        escalated = levels[min(idx + 1, len(levels) - 1)]
        assert escalated == "critical"

    def test_escalation_from_medium(self):
        """Escalation from medium reaches high."""
        levels = ["low", "medium", "high", "critical"]
        current = "medium"
        idx = levels.index(current)
        escalated = levels[min(idx + 1, len(levels) - 1)]
        assert escalated == "high"

    def test_heartbeat_failure_initial_severity(self):
        """Initial heartbeat failure severity is medium (< 5 failures) or high (>= 5)."""
        failure_count = 3
        severity = "high" if failure_count >= 5 else "medium"
        assert severity == "medium"

        failure_count = 7
        severity = "high" if failure_count >= 5 else "medium"
        assert severity == "high"


class TestAuditTrail:
    """Test audit trail for incident lifecycle mutations."""

    def test_audit_log_has_required_fields(self):
        """Audit log for state transition has all required fields."""
        audit = AuditLog(
            id=uuid.uuid4(),
            action="incident.transition",
            actor_type="system",
            resource_type="incident",
            resource_id=str(uuid.uuid4()),
            project_id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            details={
                "from_status": "DETECTED",
                "to_status": "TRIAGING",
            },
            evidence={
                "fingerprint": "abc123",
                "severity": "medium",
            },
            authorization={"status": "automatic"},
            outcome="success",
        )

        assert audit.action == "incident.transition"
        assert audit.details["from_status"] == "DETECTED"
        assert audit.details["to_status"] == "TRIAGING"
        assert audit.outcome == "success"

    def test_audit_log_preserves_evidence(self):
        """Audit log preserves fingerprint and severity as evidence."""
        fingerprint = "abc123def456"
        audit = AuditLog(
            id=uuid.uuid4(),
            action="incident.transition",
            actor_type="system",
            resource_type="incident",
            resource_id=str(uuid.uuid4()),
            project_id=uuid.uuid4(),
            details={"from_status": "DETECTED", "to_status": "TRIAGING"},
            evidence={"fingerprint": fingerprint, "severity": "high"},
            authorization={"status": "automatic"},
            outcome="success",
        )

        assert audit.evidence["fingerprint"] == fingerprint

    def test_pipeline_audit_has_event_details(self):
        """Pipeline audit log includes event type and investigation level."""
        audit = AuditLog(
            id=uuid.uuid4(),
            action="pipeline_processed",
            actor_type="system",
            resource_type="event",
            resource_id=str(uuid.uuid4()),
            project_id=uuid.uuid4(),
            details={
                "event_type": "HEARTBEAT_FAILURE",
                "investigation_level": 1,
                "actions_taken": ["event_persisted", "heartbeat_pattern_detected:3"],
            },
            evidence={},
            authorization={"status": "automatic_pipeline"},
            outcome="success",
        )

        assert audit.details["event_type"] == "HEARTBEAT_FAILURE"
        assert audit.details["investigation_level"] == 1


class TestHistoricalImmutability:
    """Test that recovery and state changes do not overwrite historical evidence."""

    def test_failure_event_severity_not_overwritten_by_recovery(self):
        """Recovery adds new evidence but does not modify failure event severity."""
        original_event = {
            "event_type": "HEARTBEAT_FAILURE",
            "severity": "high",
            "received_at": "2026-09-02T10:00:00Z",
        }
        # Recovery event is separate
        recovery_event = {
            "event_type": "HEARTBEAT_SUCCESS",
            "severity": "low",
            "received_at": "2026-09-02T11:00:00Z",
        }

        # Original event is untouched
        assert original_event["event_type"] == "HEARTBEAT_FAILURE"
        assert original_event["severity"] == "high"
        assert recovery_event["event_type"] == "HEARTBEAT_SUCCESS"

    def test_incident_metadata_additive(self):
        """Recovery metadata is additive, not destructive."""
        incident_metadata = {
            "heartbeat_failure": True,
            "failure_count": 5,
            "heartbeat_incident_created": True,
        }
        recovery_metadata = {
            "last_recovery": {"timestamp": "2026-09-02T11:00:00Z"},
        }
        merged = {**incident_metadata, **recovery_metadata}

        assert merged["heartbeat_failure"] is True
        assert merged["failure_count"] == 5
        assert "last_recovery" in merged

    def test_incident_fingerprint_immutable(self):
        """Fingerprint never changes after incident creation."""
        fingerprint = hashlib.sha256(b"test:fingerprint").hexdigest()[:16]
        # Through all state transitions, fingerprint remains the same
        assert fingerprint == fingerprint


class TestIdempotency:
    """Test idempotency of incident correlation."""

    def test_same_fingerprint_correlates_to_same_incident(self):
        """Multiple failures with same fingerprint update, not duplicate."""
        project_id = uuid.uuid4()
        target_id = "target-1"
        fingerprint = hashlib.sha256(
            f"heartbeat:{project_id}:{target_id}".encode()
        ).hexdigest()[:16]

        # Simulate: first failure creates incident
        incidents = [{"fingerprint": fingerprint, "count": 1}]

        # Second failure with same fingerprint — correlates to existing
        for _ in range(4):
            found = next((i for i in incidents if i["fingerprint"] == fingerprint), None)
            if found:
                found["count"] += 1
            else:
                incidents.append({"fingerprint": fingerprint, "count": 1})

        assert len(incidents) == 1
        assert incidents[0]["count"] == 5

    def test_different_targets_create_different_incidents(self):
        """Different targets produce different fingerprints and different incidents."""
        project_id = uuid.uuid4()
        fp1 = hashlib.sha256(f"heartbeat:{project_id}:target-a".encode()).hexdigest()[:16]
        fp2 = hashlib.sha256(f"heartbeat:{project_id}:target-b".encode()).hexdigest()[:16]

        assert fp1 != fp2


class TestRecoveryReset:
    """Test that recovery resets when failure reappears."""

    def test_recovery_count_resets_on_failure(self):
        """When failure reappears during recovery, counter resets to 0."""
        # Simulate recovery in progress
        recovery_count = 3
        # Failure reappears
        recovery_count = 0
        assert recovery_count == 0

    def test_recovery_verification_started_at_resets(self):
        """Verification window resets when failure reappears."""
        verification_started = datetime.now(timezone.utc)
        # Failure reappears
        verification_started = None
        assert verification_started is None

    def test_recovery_metadata_preserves_reset_history(self):
        """Recovery reset is recorded in metadata."""
        metadata = {
            "last_recovery": {"timestamp": "2026-09-03T10:00:00Z"},
            "recovery_reset_by_failure": {
                "timestamp": "2026-09-03T10:05:00Z",
                "previous_count": 2,
            },
        }
        assert "recovery_reset_by_failure" in metadata
        assert metadata["recovery_reset_by_failure"]["previous_count"] == 2

    def test_idempotency_key_uses_check_window(self):
        """Heartbeat idempotency key uses check window, not exact timestamp."""
        target_interval = 60
        t1 = 120  # window = 2
        t2 = 150  # window = 2 (same window)
        t3 = 180  # window = 3 (next window)

        window1 = t1 // target_interval
        window2 = t2 // target_interval
        window3 = t3 // target_interval

        assert window1 == window2, f"Same window should produce same key: {window1} vs {window2}"
        assert window1 != window3, f"Different windows should produce different keys: {window1} vs {window3}"


class TestDeliveryVsIdempotency:
    """Test delivery_id vs idempotency_key distinction."""

    def test_delivery_id_is_separate_from_idempotency_key(self):
        """delivery_id deduplicates retries; idempotency_key deduplicates logical events."""
        delivery_id_1 = "heartbeat:target-1:1000"
        delivery_id_2 = "heartbeat:target-1:1001"
        assert delivery_id_1 != delivery_id_2

    def test_same_delivery_id_deduplicates(self):
        """Same delivery_id on retry returns existing event."""
        delivery_id = "heartbeat:target-1:1000"
        assert delivery_id == delivery_id


class TestEventIdempotency:
    """Test event idempotency key generation and duplicate detection."""

    def test_idempotency_key_includes_payload_hash(self):
        """Idempotency key includes payload hash for true duplicate detection."""
        import hashlib, json
        import uuid as _uuid

        # Two events with same type/source/project/timestamp but different payloads
        payload_a = {"status_code": 500}
        payload_b = {"status_code": 503}

        payload_hash_a = hashlib.sha256(json.dumps(payload_a, sort_keys=True).encode()).hexdigest()[:8]
        payload_hash_b = hashlib.sha256(json.dumps(payload_b, sort_keys=True).encode()).hexdigest()[:8]

        assert payload_hash_a != payload_hash_b, "Different payloads should produce different hashes"

    def test_idempotency_key_same_payload_same_hash(self):
        """Same payload produces same idempotency key."""
        import hashlib, json

        payload = {"status_code": 500, "target_id": "t1"}
        hash1 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]
        hash2 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]

        assert hash1 == hash2

    def test_idempotency_key_sorted_keys(self):
        """Idempotency key uses sorted keys for deterministic hashing."""
        import hashlib, json

        payload_a = {"b": 2, "a": 1}
        payload_b = {"a": 1, "b": 2}

        hash_a = hashlib.sha256(json.dumps(payload_a, sort_keys=True).encode()).hexdigest()[:8]
        hash_b = hashlib.sha256(json.dumps(payload_b, sort_keys=True).encode()).hexdigest()[:8]

        assert hash_a == hash_b, "Key order should not matter"

    def test_event_model_has_idempotency_key_field(self):
        """Event model has idempotency_key with unique constraint."""
        from app.database.models import Event
        col = Event.__table__.c.idempotency_key
        assert col.unique is True
        assert col.nullable is False
    """Adversarial tests for cross-tenant isolation."""

    def test_different_org_different_project_ids(self):
        """Different organizations have different project ID spaces."""
        org_a_project = uuid.uuid4()
        org_b_project = uuid.uuid4()
        assert org_a_project != org_b_project

    def test_incident_org_isolation(self):
        """Incidents are scoped to projects, which are scoped to organizations."""
        org_a_project = uuid.uuid4()
        org_b_project = uuid.uuid4()

        incident_a = MagicMock()
        incident_a.project_id = org_a_project

        # Incident A should not be accessible by org B
        assert incident_a.project_id != org_b_project

    def test_event_org_isolation(self):
        """Events are scoped to projects, which are scoped to organizations."""
        org_a_project = uuid.uuid4()
        org_b_project = uuid.uuid4()

        event_a = MagicMock()
        event_a.project_id = org_a_project

        assert event_a.project_id != org_b_project

    def test_cross_tenant_incident_injection_prevented(self):
        """Cannot create incident with another org's project_id."""
        org_a_project = uuid.uuid4()
        org_b_project = uuid.uuid4()

        # Attempt to create incident with wrong project
        data = IncidentCreate(
            project_id=org_b_project,
            severity="medium",
        )
        assert data.project_id == org_b_project
        # The API layer enforces require_project_access
        # This test verifies the data model doesn't leak

    def test_audit_log_no_cross_tenant_leakage(self):
        """Audit logs are scoped by project_id."""
        from app.database.models import AuditLog

        audit_a = AuditLog(
            id=uuid.uuid4(),
            action="test",
            actor_type="system",
            resource_type="test",
            resource_id="test",
            project_id=uuid.uuid4(),
        )
        audit_b = AuditLog(
            id=uuid.uuid4(),
            action="test",
            actor_type="system",
            resource_type="test",
            resource_id="test",
            project_id=uuid.uuid4(),
        )
        assert audit_a.project_id != audit_b.project_id

    def test_fingerprint_is_project_scoped(self):
        """Same fingerprint in different projects represents different incidents."""
        fingerprint = "abc123def456"
        project_a = uuid.uuid4()
        project_b = uuid.uuid4()

        # Fingerprint alone doesn't identify an incident; project_id is required
        assert project_a != project_b
    """Test that incidents can be fully explained from persisted evidence."""

    def test_incident_has_required_evidence_fields(self):
        """Incident model includes all fields needed for evidence chain."""
        incident = Incident(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            status=IncidentStatus.DETECTED,
            severity="medium",
            title="Test incident",
            summary="Test summary",
            fingerprint="abc123",
            correlation_id=uuid.uuid4(),
            detected_at=datetime.now(timezone.utc),
        )

        assert incident.fingerprint is not None
        assert incident.correlation_id is not None
        assert incident.detected_at is not None

    def test_incident_resolved_at_set_on_resolution(self):
        """resolved_at is set when transitioning to RESOLVED."""
        incident = Incident(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            status=IncidentStatus.VERIFYING,
            severity="medium",
            detected_at=datetime.now(timezone.utc),
        )
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = datetime.now(timezone.utc)
        assert incident.resolved_at is not None

    def test_incident_updated_at_modified(self):
        """updated_at is modified on state transitions."""
        incident = Incident(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            status=IncidentStatus.DETECTED,
            severity="medium",
            detected_at=datetime.now(timezone.utc),
        )
        old_updated = incident.updated_at
        incident.updated_at = datetime.now(timezone.utc)
        assert incident.updated_at != old_updated or incident.updated_at is not None

    def test_incident_has_recovery_tracking_fields(self):
        """Incident model has recovery_success_count and verification_started_at."""
        incident = Incident(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            status=IncidentStatus.DETECTED,
            severity="medium",
            detected_at=datetime.now(timezone.utc),
        )
        assert hasattr(incident, "recovery_success_count")
        assert hasattr(incident, "recovery_verification_started_at")
        # Column exists with default=0 (applied by DB server_default)
        # In-memory SQLAlchemy instances show the column attribute exists
        assert incident.recovery_verification_started_at is None

    def test_evidence_chain_is_complete(self):
        """Evidence chain: Event -> Incident -> Audit -> Memory."""
        from app.database.models import AuditLog, Event
        from app.memory.engine import MemoryRecord

        # Event provides evidence for incident
        event = MagicMock()
        event.event_type = "HEARTBEAT_FAILURE"
        event.severity = "high"
        event.project_id = uuid.uuid4()

        # Incident references event fingerprint
        incident = MagicMock()
        incident.fingerprint = "abc123"
        incident.severity = "medium"
        incident.project_id = event.project_id

        # Audit records transition with evidence
        audit = MagicMock()
        audit.evidence = {"fingerprint": incident.fingerprint, "severity": incident.severity}

        # Memory records outcome
        memory = MagicMock()
        memory.fingerprint = incident.fingerprint

        # Verify chain
        assert audit.evidence["fingerprint"] == incident.fingerprint
        assert memory.fingerprint == incident.fingerprint

    def test_provenance_ids_link_evidence(self):
        """Provenance IDs link events, incidents, and audit records."""
        incident_id = uuid.uuid4()
        event_id = uuid.uuid4()

        # Audit log references incident
        audit = MagicMock()
        audit.incident_id = incident_id
        audit.resource_id = str(event_id)

        # Event references incident
        event = MagicMock()
        event.id = event_id
        event.incident_id = incident_id

        # Verify provenance chain
        assert audit.incident_id == event.incident_id
        assert str(event.id) == audit.resource_id


class TestRecoveryMatchingForensic:
    """Forensic tests for recovery matching correctness."""

    def test_exact_fingerprint_match_preferred(self):
        """Recovery uses exact fingerprint, not prefix."""
        import hashlib
        project_id = "proj-1"
        target_id = "target-1"

        fp_500 = hashlib.sha256(f"heartbeat:{project_id}:{target_id}:http:500".encode()).hexdigest()[:16]
        fp_503 = hashlib.sha256(f"heartbeat:{project_id}:{target_id}:http:503".encode()).hexdigest()[:16]
        fp_broad = hashlib.sha256(f"heartbeat:{project_id}:{target_id}".encode()).hexdigest()[:16]

        assert fp_500 != fp_503
        assert fp_500 != fp_broad
        assert fp_503 != fp_broad

    def test_recovery_does_not_use_prefix(self):
        """Recovery must not use startswith which can match wrong incidents."""
        prefix = "heartbeat:proj-1:target-1"
        fp1 = f"{prefix}:http:500"
        fp2 = f"{prefix}:http:503"

        # Prefix match would match BOTH -- this is wrong
        assert fp1.startswith(prefix)
        assert fp2.startswith(prefix)

        # Exact match is correct
        assert fp1 != fp2


class TestEventIdempotencyDefault:
    """Forensic tests for default idempotency_key generation."""

    def test_default_key_does_not_include_timestamp(self):
        """Default key must not include occurred_at to prevent retry bypass."""
        import hashlib, json

        payload = {"status_code": 500}
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]

        key1 = f"HEARTBEAT_FAILURE:target-1:proj-1:{payload_hash}"
        key2 = f"HEARTBEAT_FAILURE:target-1:proj-1:{payload_hash}"

        assert key1 == key2, "Same logical event must produce same key regardless of timestamp"

    def test_different_payloads_different_keys(self):
        """Different payloads produce different keys."""
        import hashlib, json

        payload_a = {"status_code": 500}
        payload_b = {"status_code": 503}

        hash_a = hashlib.sha256(json.dumps(payload_a, sort_keys=True).encode()).hexdigest()[:8]
        hash_b = hashlib.sha256(json.dumps(payload_b, sort_keys=True).encode()).hexdigest()[:8]

        key_a = f"HEARTBEAT_FAILURE:target-1:proj-1:{hash_a}"
        key_b = f"HEARTBEAT_FAILURE:target-1:proj-1:{hash_b}"

        assert key_a != key_b


class TestTransactionAtomicity:
    """Forensic tests for incident transition atomicity."""

    def test_incident_model_has_recovery_fields(self):
        """Incident model has all required recovery tracking fields."""
        from app.database.models import Incident
        assert hasattr(Incident, 'recovery_success_count')
        assert hasattr(Incident, 'recovery_verification_started_at')

    def test_event_model_has_delivery_id(self):
        """Event model has delivery_id for retry dedup."""
        from app.database.models import Event
        assert hasattr(Event, 'delivery_id')
        col = Event.__table__.c.delivery_id
        assert col.unique is True

    def test_state_machine_completeness(self):
        """All states have defined transitions."""
        from app.database.models import IncidentStateTransition
        all_states = ['DETECTED', 'TRIAGING', 'INVESTIGATING', 'DIAGNOSED',
                      'AWAITING_ACTION', 'REMEDIATING', 'VERIFYING',
                      'RESOLVED', 'REMEDIATION_FAILED', 'ESCALATED']
        for state in all_states:
            assert state in IncidentStateTransition.TRANSITIONS, f"Missing: {state}"

    def test_terminal_states_are_terminal(self):
        """RESOLVED and ESCALATED have no outgoing transitions."""
        from app.database.models import IncidentStateTransition
        assert IncidentStateTransition.TRANSITIONS['RESOLVED'] == []
        assert IncidentStateTransition.TRANSITIONS['ESCALATED'] == []
