"""
hi.myrepo - Memory Engine Tests

Tests for institutional memory search and recording.
"""
import uuid

import pytest

from app.memory.engine import MemoryCreate, MemoryEngine, MemorySearchResult


@pytest.fixture
def engine():
    return MemoryEngine()


class TestMemoryCreate:
    def test_create_record_data(self):
        data = MemoryCreate(
            incident_id=uuid.uuid4(),
            fingerprint="abc123",
            category="resolution",
            title="Checkout rollback resolved",
            summary="RB-04 rollback fixed the checkout regression",
            root_cause="Deployment 7f9b2c1 introduced TypeError",
            resolution="Rolled back to previous deployment",
            runbook_code="RB-04",
            confidence_at_resolution=0.92,
            was_autonomous=False,
            success=True,
            tags=["checkout", "regression", "rollback"],
        )
        assert data.category == "resolution"
        assert data.confidence_at_resolution == 0.92
        assert len(data.tags) == 3

    def test_create_minimal_record(self):
        data = MemoryCreate(
            category="pattern",
            title="Recurring timeout pattern",
            summary="Payment API times out during peak hours",
        )
        assert data.category == "pattern"
        assert data.was_autonomous is False
        assert data.success is True


class TestMemoryEngine:
    def test_engine_exists(self, engine):
        assert engine is not None

    def test_engine_has_required_methods(self, engine):
        assert hasattr(engine, 'record_outcome')
        assert hasattr(engine, 'search_by_fingerprint')
        assert hasattr(engine, 'search_by_category')
        assert hasattr(engine, 'search_by_tags')
        assert hasattr(engine, 'get_similar_incidents')
        assert hasattr(engine, 'get_resolution_history')


class TestMemorySearchResult:
    def test_search_result_model(self):
        result = MemorySearchResult(
            records=[{"id": "123", "title": "test"}],
            total_count=1,
            search_criteria={"fingerprint": "abc"},
        )
        assert result.total_count == 1
        assert len(result.records) == 1
