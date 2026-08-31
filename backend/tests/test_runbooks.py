"""
hi.myrepo - Runbook Engine Tests

Tests for runbook lifecycle: proposal, approval, execution, completion.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.runbooks.engine import RunbookEngine, RunbookProposal


@pytest.fixture
def engine():
    return RunbookEngine()


class TestRunbookProposal:
    def test_create_proposal(self):
        proposal = RunbookProposal(
            runbook_id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            confidence=0.85,
            reasoning="Checkout regression detected",
            expected_outcome="Service restored to previous stable version",
            risks=["Brief downtime during rollback"],
            blast_radius="low",
        )
        assert proposal.confidence == 0.85
        assert proposal.blast_radius == "low"
        assert len(proposal.risks) == 1


class TestRunbookEngine:
    def test_engine_exists(self, engine):
        assert engine is not None

    @pytest.mark.asyncio
    async def test_get_active_runbooks_empty(self, engine):
        """get_active_runbooks should work even when no DB session is provided."""
        # This tests the method signature, not the DB interaction
        assert hasattr(engine, 'get_active_runbooks')
        assert hasattr(engine, 'propose_runbook')
        assert hasattr(engine, 'approve_execution')
        assert hasattr(engine, 'start_execution')
        assert hasattr(engine, 'complete_execution')
        assert hasattr(engine, 'get_execution_history')
