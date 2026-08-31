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
