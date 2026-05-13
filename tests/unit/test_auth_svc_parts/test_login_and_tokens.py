"""
Tests for AuthService login and token management.
"""

import pytest


class TestUserLogin:
    """Tests for user authentication."""

    def test_login_success(self, auth, registered_user):
        """Should log in with correct credentials."""
        result = auth.login_user("testuser", "StrongPass1")
        assert "error" not in result
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"
        assert result["user"]["username"] == "testuser"

    def test_login_with_email(self, auth, registered_user):
        """Should log in using email instead of username."""
        result = auth.login_user("test@example.com", "StrongPass1")
        assert "error" not in result
        assert result["user"]["email"] == "test@example.com"

    def test_login_wrong_password(self, auth, registered_user):
        """Should fail with wrong password."""
        result = auth.login_user("testuser", "WrongPass1")
        assert "error" in result
        assert "credentials" in result["error"].lower()

    def test_login_nonexistent_user(self, auth):
        """Should fail for non-existent user."""
        result = auth.login_user("nouser", "SomePass123")
        assert "error" in result
        assert "credentials" in result["error"].lower()

    def test_login_deactivated_user(self, auth, registered_user):
        """Should fail for deactivated account."""
        uid = registered_user["user_id"]
        auth.deactivate_user(uid)
        result = auth.login_user("testuser", "StrongPass1")
        assert "error" in result
        assert "deactivated" in result["error"].lower()

    def test_login_updates_login_count(self, auth, registered_user):
        """Should increment login count after successful login."""
        uid = registered_user["user_id"]
        auth.login_user("testuser", "StrongPass1")
        user = auth.get_user(uid)
        assert user["login_count"] >= 1


class TestTokenManagement:
    """Tests for JWT/HMAC token creation, verification, and revocation."""

    def test_create_access_token(self, auth):
        """Should create an access token string."""
        token = auth.create_access_token(1, "user")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self, auth):
        """Should create a refresh token string."""
        token = auth.create_refresh_token(1)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_access_token(self, auth):
        """Should verify and decode a valid access token."""
        token = auth.create_access_token(1, "user")
        payload = auth.verify_token(token, "access")
        assert "error" not in payload
        assert payload["sub"] == "1"
        assert payload["role"] == "user"
        assert payload["type"] == "access"

    def test_verify_refresh_token(self, auth):
        """Should verify and decode a valid refresh token."""
        token = auth.create_refresh_token(1)
        payload = auth.verify_token(token, "refresh")
        assert "error" not in payload
        assert payload["sub"] == "1"
        assert payload["type"] == "refresh"

    def test_verify_token_wrong_type(self, auth):
        """Should reject token when type doesn't match."""
        token = auth.create_access_token(1, "user")
        payload = auth.verify_token(token, "refresh")
        assert "error" in payload
        assert "type" in payload["error"].lower()

    def test_verify_token_invalid_token(self, auth):
        """Should reject an invalid/malformed token."""
        payload = auth.verify_token("invalid.token.here", "access")
        assert "error" in payload

    def test_verify_token_empty_token(self, auth):
        """Should reject an empty token string."""
        payload = auth.verify_token("", "access")
        assert "error" in payload

    def test_revoke_token(self, auth):
        """Should revoke a token successfully."""
        token = auth.create_access_token(1, "user")
        assert auth.revoke_token(token) is True

    def test_is_token_revoked(self, auth):
        """Should detect revoked tokens."""
        token = auth.create_access_token(1, "user")
        payload = auth.verify_token(token, "access")
        jti = payload["jti"]
        assert auth.is_token_revoked(jti) is False
        auth.revoke_token(token)
        assert auth.is_token_revoked(jti) is True

    def test_revoked_token_verification_fails(self, auth):
        """Should fail verification for revoked tokens."""
        token = auth.create_access_token(1, "user")
        auth.revoke_token(token)
        payload = auth.verify_token(token, "access")
        assert "error" in payload
        assert "revoked" in payload["error"].lower()

    def test_is_token_revoked_empty_jti(self, auth):
        """Should return False for empty JTI."""
        assert auth.is_token_revoked("") is False

    def test_refresh_access_token(self, auth, registered_user):
        """Should exchange refresh token for new access + refresh tokens."""
        login_result = auth.login_user("testuser", "StrongPass1")
        refresh = login_result["refresh_token"]
        result = auth.refresh_access_token(refresh)
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"

    def test_refresh_access_token_invalid(self, auth):
        """Should fail refresh with an invalid token."""
        result = auth.refresh_access_token("invalid-token")
        assert "error" in result

    def test_create_access_token_with_extra(self, auth):
        """Should include extra claims in the access token."""
        token = auth.create_access_token(1, "user", extra={"custom": "value"})
        payload = auth.verify_token(token, "access")
        assert payload.get("custom") == "value"
