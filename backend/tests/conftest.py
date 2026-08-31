"""
hi.myrepo - Test Configuration

Shared fixtures for backend tests.
"""
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def sample_project_id():
    return uuid.uuid4()


@pytest.fixture
def sample_correlation_id():
    return uuid.uuid4()


@pytest.fixture
def sample_trace_id():
    return uuid.uuid4()


@pytest.fixture
def sample_timestamp():
    return datetime.now(timezone.utc)
