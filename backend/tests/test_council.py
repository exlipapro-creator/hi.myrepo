"""
hi.myrepo - Council Engine Tests

Tests for the bounded evidence-analysis pipeline.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.council.engine import (
    AgentEvidence,
    CouncilBudget,
    CouncilEngine,
    CouncilRole,
    CouncilVerdict,
)


@pytest.fixture
def council():
    return CouncilEngine()


@pytest.fixture
def mock_incident():
    """Create a mock incident-like object for council investigation."""

    class MockIncident:
        def __init__(self):
            self.id = uuid.uuid4()
            self.fingerprint = "abc123def456"
            self.affected_service = "checkout"
            self.affected_component = "/api/checkout"
            self.severity = "high"
            self.status = "INVESTIGATING"
            self.metadata_ = {}

    return MockIncident()


@pytest.fixture
def context_with_deployment():
    return {
        "recent_deployment": {
            "commit_sha": "7f9b2c1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "error_groups": [
            {
                "error_type": "TypeError",
                "error_message": "shippingMethod is undefined",
            }
        ],
        "dependencies": [
            {"name": "payment-api", "type": "api", "is_healthy": True},
            {"name": "inventory-db", "type": "database", "is_healthy": True},
        ],
        "heartbeat_results": [
            {"is_healthy": True, "endpoint": "/api/checkout"},
        ],
        "similar_incidents": [
            {"id": str(uuid.uuid4()), "status": "RESOLVED", "severity": "high"},
        ],
        "memory_records": [
            {"title": "Previous checkout regression", "summary": "Rollback resolved it"},
        ],
    }


class TestCouncilBudget:
    def test_max_agents(self):
        assert CouncilBudget.MAX_AGENTS == 5

    def test_max_rounds(self):
        assert CouncilBudget.MAX_ROUNDS >= 1

    def test_max_tokens(self):
        assert CouncilBudget.MAX_TOKENS > 0

    def test_max_execution_seconds(self):
        assert CouncilBudget.MAX_EXECUTION_SECONDS > 0


class TestCouncilRoles:
    def test_all_roles_exist(self):
        roles = list(CouncilRole)
        assert len(roles) == 5
        assert CouncilRole.PROSECUTOR in roles
        assert CouncilRole.INFRASTRUCTURE_DEFENDER in roles
        assert CouncilRole.HISTORICAL_ANALYST in roles
        assert CouncilRole.ADVERSARIAL_REVIEWER in roles
        assert CouncilRole.LEAD_SYNTHESIZER in roles


class TestAgentEvidence:
    def test_create_evidence(self):
        evidence = AgentEvidence(
            role=CouncilRole.PROSECUTOR,
            findings="Found error in checkout",
            confidence=0.7,
        )
        assert evidence.role == CouncilRole.PROSECUTOR
        assert evidence.confidence == 0.7
        assert len(evidence.supporting_evidence) == 0

    def test_evidence_with_challenges(self):
        evidence = AgentEvidence(
            role=CouncilRole.ADVERSARIAL_REVIEWER,
            findings="Review complete",
            confidence=0.5,
            challenges=["High confidence but limited evidence"],
        )
        assert len(evidence.challenges) == 1


class TestCouncilVerdict:
    def test_create_verdict(self):
        verdict = CouncilVerdict(
            root_cause="Checkout regression",
            confidence=0.85,
            evidence={"agents": []},
            recommended_action="RB-04 rollback",
        )
        assert verdict.confidence == 0.85
        assert verdict.root_cause == "Checkout regression"
        assert verdict.blast_radius == "medium"  # default


class TestCouncilEngine:
    @pytest.mark.asyncio
    async def test_investigate_returns_verdict(self, council, mock_incident, context_with_deployment):
        verdict = await council.investigate(mock_incident, context_with_deployment)
        assert isinstance(verdict, CouncilVerdict)
        assert 0.0 <= verdict.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_investigation_uses_agents(self, council, mock_incident, context_with_deployment):
        verdict = await council.investigate(mock_incident, context_with_deployment)
        assert len(verdict.agents_used) >= 1

    @pytest.mark.asyncio
    async def test_investigation_with_empty_context(self, council, mock_incident):
        verdict = await council.investigate(mock_incident, {})
        assert isinstance(verdict, CouncilVerdict)
        # With no evidence, confidence should be low
        assert verdict.confidence <= 0.6

    @pytest.mark.asyncio
    async def test_investigation_records_budget(self, council, mock_incident, context_with_deployment):
        verdict = await council.investigate(mock_incident, context_with_deployment)
        assert verdict.council_rounds_used >= 1

    @pytest.mark.asyncio
    async def test_prosecutor_identifies_deployment(self, council, mock_incident, context_with_deployment):
        evidence = await council._run_prosecutor(mock_incident, context_with_deployment)
        assert evidence.role == CouncilRole.PROSECUTOR
        assert "7f9b2c1" in evidence.findings

    @pytest.mark.asyncio
    async def test_prosecutor_handles_no_deployment(self, council, mock_incident):
        evidence = await council._run_prosecutor(mock_incident, {})
        assert evidence.role == CouncilRole.PROSECUTOR
        assert any("No deployment" in c for c in evidence.challenges)

    @pytest.mark.asyncio
    async def test_defender_checks_infrastructure(self, council, mock_incident, context_with_deployment):
        evidence = await council._run_defender(mock_incident, context_with_deployment)
        assert evidence.role == CouncilRole.INFRASTRUCTURE_DEFENDER
        assert "All reported dependencies are healthy" in evidence.findings

    @pytest.mark.asyncio
    async def test_defender_detects_unhealthy_deps(self, council, mock_incident):
        context = {
            "dependencies": [
                {"name": "payment-api", "type": "api", "is_healthy": False},
            ]
        }
        evidence = await council._run_defender(mock_incident, context)
        assert "Unhealthy dependencies" in evidence.findings

    @pytest.mark.asyncio
    async def test_historical_analyst_finds_precedent(self, council, mock_incident, context_with_deployment):
        evidence = await council._run_historical_analyst(mock_incident, context_with_deployment)
        assert evidence.role == CouncilRole.HISTORICAL_ANALYST
        assert "similar" in evidence.findings.lower()

    @pytest.mark.asyncio
    async def test_adversarial_reviewer_challenges(self, council, mock_incident, context_with_deployment):
        prosecutor = await council._run_prosecutor(mock_incident, context_with_deployment)
        reviewer = await council._run_adversarial_reviewer(mock_incident, [prosecutor])
        assert reviewer.role == CouncilRole.ADVERSARIAL_REVIEWER
        assert "Adversarial review completed" in reviewer.findings

    @pytest.mark.asyncio
    async def test_synthesizer_aggregates(self, council, mock_incident, context_with_deployment):
        prosecutor = await council._run_prosecutor(mock_incident, context_with_deployment)
        defender = await council._run_defender(mock_incident, context_with_deployment)
        evidence = await council._run_synthesizer(mock_incident, [prosecutor, defender])
        assert evidence.role == CouncilRole.LEAD_SYNTHESIZER
        assert evidence.confidence > 0

    @pytest.mark.asyncio
    async def test_investigation_budget_not_exceeded(self, council, mock_incident, context_with_deployment):
        verdict = await council.investigate(mock_incident, context_with_deployment)
        # With default budget, should complete within limits
        assert verdict.council_rounds_used <= CouncilBudget.MAX_ROUNDS
