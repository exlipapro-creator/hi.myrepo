"""
hi.myrepo - Authentication Tests

Tests for JWT token creation, validation, password hashing, and role enforcement.
"""
import uuid
from datetime import timedelta

import pytest

from app.security.auth import (
    TokenData,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_password(self):
        hashed = hash_password("test-password-123")
        assert hashed != "test-password-123"
        assert len(hashed) > 20

    def test_verify_correct_password(self):
        hashed = hash_password("my-secret-password")
        assert verify_password("my-secret-password", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("my-secret-password")
        assert verify_password("wrong-password", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        # bcrypt produces different salts, so hashes should differ
        assert h1 != h2

    def test_verify_roundtrip(self):
        pw = "complex-p@ssw0rd!2024"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)


class TestJWTToken:
    def test_create_and_decode_token(self):
        token = create_access_token(
            user_id="user-123",
            email="test@example.com",
            role="admin",
            organization_id="org-456",
            autonomy_level=2,
        )
        assert isinstance(token, str)
        assert len(token) > 50

        data = decode_token(token)
        assert data.user_id == "user-123"
        assert data.email == "test@example.com"
        assert data.role == "admin"
        assert data.organization_id == "org-456"
        assert data.autonomy_level == 2

    def test_token_with_custom_expiry(self):
        token = create_access_token(
            user_id="user-123",
            email="test@example.com",
            role="viewer",
            organization_id="org-456",
            autonomy_level=0,
            expires_delta=timedelta(minutes=5),
        )
        data = decode_token(token)
        assert data.user_id == "user-123"

    def test_invalid_token_raises(self):
        with pytest.raises(Exception):
            decode_token("not-a-valid-jwt-token")

    def test_empty_token_raises(self):
        with pytest.raises(Exception):
            decode_token("")

    def test_tampered_token_raises(self):
        token = create_access_token(
            user_id="user-123",
            email="test@example.com",
            role="admin",
            organization_id="org-456",
            autonomy_level=2,
        )
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(Exception):
            decode_token(tampered)


class TestTokenData:
    def test_token_data_model(self):
        data = TokenData(
            user_id="user-123",
            email="test@example.com",
            role="admin",
            organization_id="org-456",
            autonomy_level=2,
        )
        assert data.user_id == "user-123"
        assert data.role == "admin"


# ============================================================================
# /auth/me endpoint regression tests
# ============================================================================


class TestGetMeEndpoint:
    """Regression tests for GET /auth/me — must load user from PostgreSQL."""

    @pytest.mark.asyncio
    async def test_me_returns_full_user_profile(self):
        """Authenticated user gets their full profile from the database."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth import router
        from app.security.auth import create_access_token

        user_id = uuid.uuid4()
        org_id = uuid.uuid4()

        # Create a real JWT
        token = create_access_token(
            user_id=str(user_id),
            email="test@example.com",
            role="admin",
            organization_id=str(org_id),
            autonomy_level=2,
        )

        # Mock DB user record
        mock_db_user = MagicMock()
        mock_db_user.id = user_id
        mock_db_user.email = "test@example.com"
        mock_db_user.full_name = "Test User"
        mock_db_user.role = "admin"
        mock_db_user.autonomy_level = 2
        mock_db_user.organization_id = org_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with patch("app.api.auth.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            client = TestClient(app)
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(user_id)
            assert data["email"] == "test@example.com"
            assert data["full_name"] == "Test User"
            assert data["role"] == "admin"
            assert data["autonomy_level"] == 2
            assert data["organization_id"] == str(org_id)

    @pytest.mark.asyncio
    async def test_me_returns_404_for_nonexistent_user(self):
        """Valid JWT referencing a deleted user returns 404."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth import router
        from app.security.auth import create_access_token

        user_id = uuid.uuid4()
        org_id = uuid.uuid4()

        token = create_access_token(
            user_id=str(user_id),
            email="deleted@example.com",
            role="admin",
            organization_id=str(org_id),
            autonomy_level=2,
        )

        # DB returns None — user was deleted
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with patch("app.api.auth.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            client = TestClient(app)
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 404
            assert response.json()["detail"] == "User not found"

    @pytest.mark.asyncio
    async def test_me_returns_null_full_name_when_not_set(self):
        """Users with no full_name set get null (not an error)."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth import router
        from app.security.auth import create_access_token

        user_id = uuid.uuid4()
        org_id = uuid.uuid4()

        token = create_access_token(
            user_id=str(user_id),
            email="noname@example.com",
            role="member",
            organization_id=str(org_id),
            autonomy_level=1,
        )

        mock_db_user = MagicMock()
        mock_db_user.id = user_id
        mock_db_user.email = "noname@example.com"
        mock_db_user.full_name = None
        mock_db_user.role = "member"
        mock_db_user.autonomy_level = 1
        mock_db_user.organization_id = org_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        with patch("app.api.auth.db_manager") as mock_db:
            mock_db.get_session.return_value = mock_session_ctx

            client = TestClient(app)
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["full_name"] is None
            assert data["email"] == "noname@example.com"

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self):
        """Request without JWT is rejected before reaching the endpoint."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        client = TestClient(app)
        response = client.get("/api/v1/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_invalid_token_returns_401(self):
        """Request with invalid JWT is rejected."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")

        client = TestClient(app)
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401
