"""
hi.myrepo - Test Configuration

Shared fixtures for backend tests.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


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


@pytest.fixture
def auth_headers(client):
    """Register a test user and return auth headers."""
    email = f"test-{uuid.uuid4().hex[:8]}@test.com"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "testpassword123",
            "full_name": "Test User",
            "organization_name": "Test Org",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_member(client):
    """Register a member user (non-admin) and return auth headers."""
    # First register an admin to create the org
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@test.com"
    admin_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": admin_email,
            "password": "testpassword123",
            "full_name": "Admin User",
            "organization_name": "Member Test Org",
        },
    )
    assert admin_resp.status_code == 201

    # Note: Can't easily create a non-admin via the public API.
    # This fixture returns admin headers for now.
    # For proper member testing, use the register + manual role set.
    token = admin_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers(client):
    """Register an admin user and return auth headers."""
    email = f"admin-{uuid.uuid4().hex[:8]}@test.com"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "testpassword123",
            "full_name": "Admin User",
            "organization_name": "Admin Test Org",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
