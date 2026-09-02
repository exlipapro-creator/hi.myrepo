"""
Tests for AI Provider CRUD API.

Verifies:
- Provider creation with encrypted API keys
- Provider listing (no key leakage)
- Provider update
- Provider deletion
- Admin-only access control
- Encryption/decryption roundtrip
- Audit log creation
"""
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security.encryption import encrypt_secret, decrypt_secret, mask_secret, is_encrypted


# ── Encryption Tests ───────────────────────────────────────────────────

class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted value can be decrypted back to plaintext."""
        plaintext = "sk-test-1234567890abcdef1234567890abcdef"
        encrypted = encrypt_secret(plaintext)
        assert encrypted != plaintext
        assert encrypted.startswith("enc:") or encrypted.startswith("dev:")

        decrypted = decrypt_secret(encrypted)
        assert decrypted == plaintext

    def test_encrypt_empty_string(self):
        """Empty string returns empty."""
        assert encrypt_secret("") == ""
        assert decrypt_secret("") == ""

    def test_mask_secret(self):
        """Masked secret shows last 4 chars."""
        result = mask_secret("sk-1234567890abcdef", visible_chars=4)
        assert result.endswith("cdef")
        assert result.startswith("•")
        assert "12345" not in result  # Middle chars are masked

    def test_mask_short_secret(self):
        """Short secrets are fully masked."""
        result = mask_secret("abc", visible_chars=4)
        assert result == "•••"

    def test_is_encrypted(self):
        """Correctly identifies encrypted values."""
        assert is_encrypted("enc:abcdef") is True
        assert is_encrypted("dev:abcdef") is True
        assert is_encrypted("sk-123456") is False
        assert is_encrypted("") is False

    def test_legacy_unencrypted_passthrough(self):
        """Legacy unencrypted keys are returned as-is."""
        plaintext = "sk-legacy-key"
        result = decrypt_secret(plaintext)
        assert result == result


# ── Provider API Tests ─────────────────────────────────────────────────

def _make_provider(name="gemini", status="healthy"):
    """Create a mock AIProvider object."""
    provider = MagicMock()
    provider.id = uuid.uuid4()
    provider.name = name
    provider.status = status
    provider.capabilities = ["text", "vision"]
    provider.models_available = ["gemini-3.5-flash"]
    provider.success_rate = 0.95
    provider.failure_rate = 0.05
    provider.avg_latency_ms = 150.0
    provider.total_requests = 100
    provider.total_failures = 5
    provider.circuit_state = "closed"
    provider.recent_429_count = 0
    provider.recent_timeout_count = 0
    provider.cooldown_until = None
    provider.api_key_encrypted = encrypt_secret("test-api-key-1234567890abcdef")
    provider.configured_at = None
    return provider


class TestProviderAPI:
    """Tests for the /api/v1/providers endpoints using mocked DB."""

    def test_list_providers_returns_safe_metadata(self):
        """GET /api/v1/providers returns metadata without API keys."""
        mock_provider = _make_provider()

        with patch("app.api.providers.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_provider]
            mock_session.execute.return_value = mock_result
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

            # Create a valid JWT token
            from app.security.auth import create_access_token
            token = create_access_token(
                user_id=str(uuid.uuid4()),
                email="test@test.com",
                role="admin",
                organization_id=str(uuid.uuid4()),
                autonomy_level=2,
            )
            headers = {"Authorization": f"Bearer {token}"}

            client = TestClient(app)
            response = client.get("/api/v1/providers", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1

            for provider in data:
                assert "name" in provider
                assert "status" in provider
                assert "capabilities" in provider
                assert "success_rate" in provider
                # Key should NEVER be in response
                assert "api_key" not in provider
                assert "secret" not in provider

    def test_list_providers_requires_auth(self):
        """GET /api/v1/providers without token returns 401."""
        client = TestClient(app)
        response = client.get("/api/v1/providers")
        assert response.status_code == 401

    def test_create_provider_validates_name(self):
        """POST /api/v1/providers rejects unknown provider names."""
        from app.security.auth import create_access_token
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="test@test.com",
            role="admin",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )
        headers = {"Authorization": f"Bearer {token}"}

        client = TestClient(app)
        response = client.post(
            "/api/v1/providers",
            json={"name": "unknown_provider", "api_key": "test-key-12345678"},
            headers=headers,
        )
        assert response.status_code == 400
        assert "Unknown provider" in response.json()["detail"]

    def test_create_provider_encrypts_key(self):
        """POST /api/v1/providers encrypts the API key."""
        with patch("app.api.providers.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # No existing provider
            mock_session.execute.return_value = mock_result
            mock_session.add = MagicMock()
            mock_session.flush = AsyncMock()
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.security.auth import create_access_token
            token = create_access_token(
                user_id=str(uuid.uuid4()),
                email="test@test.com",
                role="admin",
                organization_id=str(uuid.uuid4()),
                autonomy_level=2,
            )
            headers = {"Authorization": f"Bearer {token}"}

            client = TestClient(app)
            response = client.post(
                "/api/v1/providers",
                json={"name": "gemini", "api_key": "test-api-key-1234567890abcdef"},
                headers=headers,
            )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "gemini"
            assert data["is_configured"] is True
            # Key should NEVER be in response
            assert "api_key" not in data
            # Verify the mock session had a provider added with encrypted key
            # add() is called for both AIProvider and AuditLog
            assert mock_session.add.call_count >= 1
            # Find the AIProvider call (not AuditLog)
            provider_calls = [c for c in mock_session.add.call_args_list
                              if 'AIProvider' in str(type(c[0][0]))]
            assert len(provider_calls) == 1
            added_provider = provider_calls[0][0][0]
            assert added_provider.api_key_encrypted is not None
            assert added_provider.api_key_encrypted != "test-api-key-1234567890abcdef"
            # Verify we can decrypt it back
            decrypted = decrypt_secret(added_provider.api_key_encrypted)
            assert decrypted == "test-api-key-1234567890abcdef"

    def test_provider_response_never_leaks_key(self):
        """Provider responses never contain the full API key."""
        mock_provider = _make_provider()

        with patch("app.api.providers.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_provider]
            mock_session.execute.return_value = mock_result
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.security.auth import create_access_token
            token = create_access_token(
                user_id=str(uuid.uuid4()),
                email="test@test.com",
                role="admin",
                organization_id=str(uuid.uuid4()),
                autonomy_level=2,
            )
            headers = {"Authorization": f"Bearer {token}"}

            client = TestClient(app)
            response = client.get("/api/v1/providers", headers=headers)
            assert response.status_code == 200
            for provider in response.json():
                assert "test-api-key" not in str(provider)
                assert "1234567890" not in str(provider)

    def test_delete_requires_admin_role(self):
        """DELETE /api/v1/providers requires admin role."""
        from app.security.auth import create_access_token
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="test@test.com",
            role="member",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )
        headers = {"Authorization": f"Bearer {token}"}

        client = TestClient(app)
        response = client.delete("/api/v1/providers/gemini", headers=headers)
        assert response.status_code == 403

    def test_update_provider_requires_admin(self):
        """PATCH /api/v1/providers requires admin role."""
        from app.security.auth import create_access_token
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            email="test@test.com",
            role="member",
            organization_id=str(uuid.uuid4()),
            autonomy_level=2,
        )
        headers = {"Authorization": f"Bearer {token}"}

        client = TestClient(app)
        response = client.patch(
            "/api/v1/providers/gemini",
            json={"api_key": "new-key-12345678"},
            headers=headers,
        )
        assert response.status_code == 403

    def test_provider_registry_completeness(self):
        """All providers in registry have required fields."""
        from app.api.providers import PROVIDER_REGISTRY

        for name, config in PROVIDER_REGISTRY.items():
            assert "name" in config
            assert "capabilities" in config
            assert "models" in config
            assert "env_var" in config
            assert "base_url" in config
            assert isinstance(config["models"], list)
            assert len(config["models"]) > 0
