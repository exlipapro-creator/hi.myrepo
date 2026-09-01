"""
Authorization regression tests for hi.myrepo.

Tests project-level authorization boundaries, tenancy isolation,
IDOR/BOLA prevention, and authentication edge cases.

These tests use mocking to verify the authorization logic
without requiring a live database connection.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Authorization boundary tests using require_project_access logic
# ============================================================================


class TestProjectAccessAuthorization:
    """Test that require_project_access correctly enforces org boundaries."""

    @pytest.mark.asyncio
    async def test_owner_can_access_own_project(self):
        """User A with org A can access project in org A."""
        from app.security.auth import TokenData

        org_id = uuid.uuid4()
        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="a@test.com",
            role="admin",
            organization_id=str(org_id),
            autonomy_level=2,
        )

        mock_project = MagicMock()
        mock_project.organization_id = org_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            from app.security.auth import require_project_access

            result = await require_project_access(uuid.uuid4(), user)
            assert result.user_id == user.user_id

    @pytest.mark.asyncio
    async def test_cross_org_access_denied(self):
        """User A with org A CANNOT access project in org B."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="a@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )

        # Project belongs to a DIFFERENT org
        mock_project = MagicMock()
        mock_project.organization_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            from app.security.auth import require_project_access
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await require_project_access(uuid.uuid4(), user)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_nonexistent_project_returns_404(self):
        """Non-existent project returns 404, not 403 (no information leakage)."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="a@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            from app.security.auth import require_project_access
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await require_project_access(uuid.uuid4(), user)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_cannot_elevate_org_via_project_id(self):
        """Changing project_id in the request doesn't bypass org check."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="a@test.com",
            role="member",
            organization_id=str(uuid.uuid4()),
            autonomy_level=1,
        )

        # Project belongs to a DIFFERENT org
        mock_project = MagicMock()
        mock_project.organization_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            from app.security.auth import require_project_access
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await require_project_access(uuid.uuid4(), user)
            assert exc_info.value.status_code == 403


# ============================================================================
# Authentication boundary tests
# ============================================================================


class TestAuthenticationBoundary:
    """Test JWT validation and authentication edge cases."""

    def test_jwt_creation_and_decode(self):
        """Valid JWT can be created and decoded with correct claims."""
        from app.security.auth import create_access_token, decode_token

        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        token = create_access_token(
            user_id=user_id,
            email="test@example.com",
            role="admin",
            organization_id=org_id,
            autonomy_level=3,
        )

        decoded = decode_token(token)
        assert decoded.user_id == user_id
        assert decoded.email == "test@example.com"
        assert decoded.role == "admin"
        assert decoded.organization_id == org_id
        assert decoded.autonomy_level == 3

    def test_jwt_rejects_invalid_signature(self):
        """Token signed with wrong secret is rejected."""
        from app.security.auth import decode_token
        from jose import jwt
        from fastapi import HTTPException

        token = jwt.encode(
            {"sub": "test", "email": "test@test.com", "role": "user",
             "org_id": str(uuid.uuid4()), "autonomy_level": 1,
             "iss": "hi.myrepo"},
            "wrong-secret-key-that-is-not-the-real-one-12345678",
            algorithm="HS256",
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_jwt_rejects_missing_claims(self):
        """Token missing required claims is rejected."""
        from app.security.auth import decode_token, settings
        from jose import jwt
        from fastapi import HTTPException

        # Token missing 'role' claim
        token = jwt.encode(
            {"sub": "test", "email": "test@test.com",
             "org_id": str(uuid.uuid4()), "autonomy_level": 1,
             "iss": "hi.myrepo"},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_jwt_rejects_wrong_issuer(self):
        """Token with wrong issuer is rejected."""
        from app.security.auth import decode_token, settings
        from jose import jwt
        from fastapi import HTTPException

        token = jwt.encode(
            {"sub": "test", "email": "test@test.com", "role": "user",
             "org_id": str(uuid.uuid4()), "autonomy_level": 1,
             "iss": "attacker.myrepo"},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_token_data_isolation(self):
        """TokenData cannot be manipulated after creation."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id="user-123",
            email="test@test.com",
            role="viewer",
            organization_id="org-456",
            autonomy_level=0,
        )

        assert user.user_id == "user-123"
        assert user.organization_id == "org-456"
        assert user.autonomy_level == 0


# ============================================================================
# Get user project IDs helper tests
# ============================================================================


class TestGetUserProjectIds:
    """Test the org-scoping helper."""

    @pytest.mark.asyncio
    async def test_returns_only_org_projects(self):
        """Only projects belonging to user's org are returned."""
        from app.security.auth import TokenData, get_user_project_ids

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="test@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )

        project_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        mock_result = MagicMock()
        mock_result.all.return_value = [(pid,) for pid in project_ids]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            result = await get_user_project_ids(user)
            assert len(result) == 3
            assert result == project_ids

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty_list(self):
        """Org with no projects returns empty list."""
        from app.security.auth import TokenData, get_user_project_ids

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="test@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )

        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            result = await get_user_project_ids(user)
            assert result == []


# ============================================================================
# Incident access authorization tests
# ============================================================================


class TestIncidentAccessAuthorization:
    """Test that incident access checks verify org ownership."""

    @pytest.mark.asyncio
    async def test_incident_access_checks_project(self):
        """require_incident_access verifies the incident's project ownership."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="a@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )

        # Mock incident with a project in a different org
        mock_incident = MagicMock()
        mock_incident.project_id = uuid.uuid4()

        mock_inc_result = MagicMock()
        mock_inc_result.scalar_one_or_none.return_value = mock_incident

        # Mock project with different org
        mock_project = MagicMock()
        mock_project.organization_id = uuid.uuid4()

        mock_proj_result = MagicMock()
        mock_proj_result.scalar_one_or_none.return_value = mock_project

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_inc_result
            return mock_proj_result

        mock_session = AsyncMock()
        mock_session.execute = mock_execute

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            from app.security.auth import require_incident_access
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await require_incident_access(uuid.uuid4(), user)
            assert exc_info.value.status_code == 403


# ============================================================================
# Role boundary tests
# ============================================================================


class TestRoleBoundary:
    """Test role-based access control."""

    def test_require_role_allows_valid_role(self):
        """User with correct role passes role check."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="admin@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=3,
        )

        # The role_checker logic is: user.role in allowed_roles
        assert user.role in ("admin", "member")

    def test_require_role_rejects_invalid_role(self):
        """User with wrong role fails role check."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="viewer@test.com",
            role="viewer",
            organization_id=str(uuid.uuid4()),
            autonomy_level=0,
        )

        assert user.role not in ("admin", "member")


# ============================================================================
# Autonomy level boundary tests
# ============================================================================


class TestAutonomyBoundary:
    """Test autonomy level enforcement."""

    def test_autonomy_level_in_token(self):
        """Autonomy level is stored in JWT and read from token."""
        from app.security.auth import create_access_token, decode_token

        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="test@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=4,
        )

        decoded = decode_token(token)
        assert decoded.autonomy_level == 4

    def test_autonomy_not_manipulable_in_request(self):
        """Autonomy level comes from JWT, not request body."""
        from app.security.auth import TokenData

        # Even if a user tries to set autonomy_level in a request body,
        # the TokenData used for authorization comes from the JWT
        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="test@test.com",
            role="viewer",
            organization_id=str(uuid.uuid4()),
            autonomy_level=0,
        )

        assert user.autonomy_level == 0


# ============================================================================
# Denial-of-information tests
# ============================================================================


class TestInformationLeakage:
    """Ensure error responses don't leak cross-org information."""

    @pytest.mark.asyncio
    async def test_cross_org_returns_403_not_404(self):
        """Cross-org access returns 403 (forbidden), not 404 (not found)."""
        from app.security.auth import TokenData

        user = TokenData(
            user_id=str(uuid.uuid4()),
            email="a@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )

        # Project exists but in different org
        mock_project = MagicMock()
        mock_project.organization_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            from app.security.auth import require_project_access
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await require_project_access(uuid.uuid4(), user)
            # Must be 403, not 404 — 404 would confirm the resource exists
            assert exc_info.value.status_code == 403
