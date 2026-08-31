"""
Tests for deployment ingestion.
"""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from app.api.deployments import DeploymentCreate, DeploymentResponse


class TestDeploymentCreate:
    """Test deployment creation model."""

    def test_valid_deployment(self):
        dep = DeploymentCreate(
            project_id=uuid.uuid4(),
            status="succeeded",
            commit_sha="abc123",
        )
        assert dep.status == "succeeded"
        assert dep.environment == "production"
        assert dep.source == "api"

    def test_deployment_with_all_fields(self):
        dep = DeploymentCreate(
            project_id=uuid.uuid4(),
            environment="staging",
            status="failed",
            commit_sha="abc123",
            commit_message="fix: resolve checkout bug",
            branch="main",
            version="1.2.3",
            deployed_by="github-actions",
            source="github",
            deployment_url="https://example.com/deploy/123",
        )
        assert dep.environment == "staging"
        assert dep.source == "github"
        assert dep.version == "1.2.3"


class TestDeploymentResponse:
    """Test deployment response model."""

    def test_response_fields(self):
        resp = DeploymentResponse(
            id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            environment="production",
            status="succeeded",
            commit_sha="abc123",
            commit_message="fix: bug",
            branch="main",
            version="1.0.0",
            source="github",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        assert resp.status == "succeeded"
        assert resp.source == "github"
        assert resp.environment == "production"
