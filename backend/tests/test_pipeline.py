"""
Tests for the Pipeline Orchestrator.

Tests the end-to-end event flow:
- Event persistence
- Fingerprinting
- Error group deduplication
- Incident creation
- Investigation level determination
- Council invocation
- Policy evaluation
- Memory recording
- Audit logging
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.events.spine import EventEnvelope
from app.pipeline.orchestrator import (
    InvestigationLevel,
    PipelineOrchestrator,
    PipelineResult,
)


class TestPipelineResult:
    """Test PipelineResult model."""

    def test_empty_result(self):
        result = PipelineResult()
        assert result.event is None
        assert result.fingerprint is None
        assert result.incident is None
        assert result.investigation_level == InvestigationLevel.OBSERVE
        assert result.actions_taken == []
        assert result.errors == []

    def test_to_dict(self):
        result = PipelineResult()
        d = result.to_dict()
        assert "event_id" in d
        assert "fingerprint" in d
        assert "investigation_level" in d
        assert "actions_taken" in d
        assert "errors" in d


class TestInvestigationLevel:
    """Test investigation level determination."""

    def test_level_values(self):
        assert InvestigationLevel.OBSERVE.value == 0
        assert InvestigationLevel.CORRELATE.value == 1
        assert InvestigationLevel.LIGHTWEIGHT_AI.value == 2
        assert InvestigationLevel.FULL_COUNCIL.value == 3
        assert InvestigationLevel.EMERGENCY.value == 4

    def test_levels_are_ordered(self):
        assert InvestigationLevel.OBSERVE < InvestigationLevel.CORRELATE
        assert InvestigationLevel.CORRELATE < InvestigationLevel.LIGHTWEIGHT_AI
        assert InvestigationLevel.LIGHTWEIGHT_AI < InvestigationLevel.FULL_COUNCIL
        assert InvestigationLevel.FULL_COUNCIL < InvestigationLevel.EMERGENCY


class TestPipelineOrchestrator:
    """Test PipelineOrchestrator methods."""

    def test_orchestrator_exists(self):
        from app.pipeline.orchestrator import pipeline
        assert pipeline is not None
        assert isinstance(pipeline, PipelineOrchestrator)

    def test_thresholds_defined(self):
        orchestrator = PipelineOrchestrator()
        assert orchestrator.ERROR_GROUP_THRESHOLD_FOR_INCIDENT == 3
        assert orchestrator.SEVERITY_FOR_COUNCIL == "high"
        assert orchestrator.SEVERITY_FOR_LIGHTWEIGHT_AI == "medium"

    def test_calculate_severity_low_occurrences(self):
        orchestrator = PipelineOrchestrator()
        assert orchestrator._calculate_severity(1, "low") == "low"

    def test_calculate_severity_medium_occurrences(self):
        orchestrator = PipelineOrchestrator()
        assert orchestrator._calculate_severity(5, "low") == "medium"

    def test_calculate_severity_high_occurrences(self):
        orchestrator = PipelineOrchestrator()
        assert orchestrator._calculate_severity(20, "low") == "high"

    def test_calculate_severity_critical_occurrences(self):
        orchestrator = PipelineOrchestrator()
        assert orchestrator._calculate_severity(50, "low") == "critical"

    def test_calculate_severity_event_severity_escalation(self):
        orchestrator = PipelineOrchestrator()
        # High event severity + many occurrences = critical
        assert orchestrator._calculate_severity(50, "high") == "critical"

    def test_calculate_severity_none_event_uses_low(self):
        orchestrator = PipelineOrchestrator()
        assert orchestrator._calculate_severity(1, None) == "low"

    def test_determine_investigation_level_heartbeat_success(self):
        orchestrator = PipelineOrchestrator()
        event = MagicMock()
        event.event_type = "HEARTBEAT_SUCCESS"
        event.severity = "low"
        result = PipelineResult()
        level = orchestrator._determine_investigation_level(event, result)
        assert level == InvestigationLevel.OBSERVE

    def test_determine_investigation_level_heartbeat_failure(self):
        orchestrator = PipelineOrchestrator()
        event = MagicMock()
        event.event_type = "HEARTBEAT_FAILURE"
        event.severity = "high"
        result = PipelineResult()
        level = orchestrator._determine_investigation_level(event, result)
        assert level == InvestigationLevel.CORRELATE

    def test_determine_investigation_level_error_high_severity(self):
        orchestrator = PipelineOrchestrator()
        event = MagicMock()
        event.event_type = "ERROR_DETECTED"
        event.severity = "high"
        result = PipelineResult()
        # With error_group with enough occurrences
        result.error_group = MagicMock()
        result.error_group.occurrence_count = 5
        level = orchestrator._determine_investigation_level(event, result)
        assert level == InvestigationLevel.FULL_COUNCIL

    def test_determine_investigation_level_error_medium_severity(self):
        orchestrator = PipelineOrchestrator()
        event = MagicMock()
        event.event_type = "ERROR_DETECTED"
        event.severity = "medium"
        result = PipelineResult()
        result.error_group = MagicMock()
        result.error_group.occurrence_count = 5
        level = orchestrator._determine_investigation_level(event, result)
        assert level == InvestigationLevel.LIGHTWEIGHT_AI

    def test_determine_investigation_level_deployment_failed(self):
        orchestrator = PipelineOrchestrator()
        event = MagicMock()
        event.event_type = "DEPLOYMENT_FAILED"
        event.severity = "high"
        result = PipelineResult()
        level = orchestrator._determine_investigation_level(event, result)
        assert level == InvestigationLevel.LIGHTWEIGHT_AI

    def test_determine_investigation_level_deployment_succeeded(self):
        orchestrator = PipelineOrchestrator()
        event = MagicMock()
        event.event_type = "DEPLOYMENT_SUCCEEDED"
        event.severity = "low"
        result = PipelineResult()
        level = orchestrator._determine_investigation_level(event, result)
        assert level == InvestigationLevel.OBSERVE

    def test_determine_investigation_level_unknown_event(self):
        orchestrator = PipelineOrchestrator()
        event = MagicMock()
        event.event_type = "UNKNOWN_EVENT"
        event.severity = "low"
        result = PipelineResult()
        level = orchestrator._determine_investigation_level(event, result)
        assert level == InvestigationLevel.OBSERVE
