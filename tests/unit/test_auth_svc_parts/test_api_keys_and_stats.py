"""
Tests for AuthService API keys, validation, and stats.
"""

import pytest

from src.core.auth_service import AuthService, ROLE_HIERARCHY, ROLE_PERMISSIONS


class TestAPIKeys:
    """Tests for API key authentication."""

    def test_create_api_key(self, auth, registered_user):
        """Should create an API key for a user."""
        uid = registered_user["user_id"]
        result = auth.create_api_key(uid, "test-key", ["read", "write"])
        assert "error" not in result
        assert "api_key" in result
        assert result["api_key"].startswith("zenic_")
        assert result["name"] == "test-key"
        assert result["permissions"] == ["read", "write"]

    def test_create_api_key_nonexistent_user(self, auth):
        """Should fail for non-existent user."""
        result = auth.create_api_key(99999, "test-key")
        assert "error" in result

    def test_create_api_key_deactivated_user(self, auth, registered_user):
        """Should fail for deactivated user."""
        uid = registered_user["user_id"]
        auth.deactivate_user(uid)
        result = auth.create_api_key(uid, "test-key")
        assert "error" in result

    def test_verify_api_key(self, auth, registered_user):
        """Should verify a valid API key."""
        uid = registered_user["user_id"]
        key_result = auth.create_api_key(uid, "test-key", ["read"])
        api_key = key_result["api_key"]
        identity = auth.verify_api_key(api_key)
        assert identity is not None
        assert identity["user_id"] == uid
        assert identity["name"] == "test-key"
        assert "read" in identity["permissions"]

    def test_verify_api_key_invalid(self, auth):
        """Should return None for invalid API key."""
        assert auth.verify_api_key("invalid_key") is None

    def test_verify_api_key_wrong_prefix(self, auth):
        """Should return None for key without zenic_ prefix."""
        assert auth.verify_api_key("wrong_prefix_abc123") is None

    def test_verify_api_key_empty(self, auth):
        """Should return None for empty API key."""
        assert auth.verify_api_key("") is None

    def test_verify_api_key_revoked(self, auth, registered_user):
        """Should return None for revoked API key."""
        uid = registered_user["user_id"]
        key_result = auth.create_api_key(uid, "test-key")
        key_id = key_result["key_id"]
        api_key = key_result["api_key"]
        auth.revoke_api_key(key_id)
        assert auth.verify_api_key(api_key) is None

    def test_revoke_api_key(self, auth, registered_user):
        """Should revoke an API key."""
        uid = registered_user["user_id"]
        key_result = auth.create_api_key(uid, "test-key")
        key_id = key_result["key_id"]
        assert auth.revoke_api_key(key_id) is True

    def test_revoke_api_key_nonexistent(self, auth):
        """Should return False for non-existent key ID."""
        assert auth.revoke_api_key("nonexistent_key_id") is False

    def test_list_api_keys(self, auth, registered_user):
        """Should list API keys for a user."""
        uid = registered_user["user_id"]
        auth.create_api_key(uid, "key1")
        auth.create_api_key(uid, "key2")
        keys = auth.list_api_keys(uid)
        assert isinstance(keys, list)
        assert len(keys) >= 2


class TestValidation:
    """Tests for the _validate_registration static method."""

    def test_valid_inputs(self):
        """Should return empty list for valid inputs."""
        errors = AuthService._validate_registration("validuser", "valid@example.com", "StrongPass1")
        assert errors == []

    def test_short_username(self):
        """Should report username too short."""
        errors = AuthService._validate_registration("ab", "e@example.com", "StrongPass1")
        assert any("3 characters" in e for e in errors)

    def test_long_username(self):
        """Should report username too long."""
        errors = AuthService._validate_registration("a" * 51, "e@example.com", "StrongPass1")
        assert any("50 characters" in e for e in errors)

    def test_invalid_username_chars(self):
        """Should report invalid username characters."""
        errors = AuthService._validate_registration("user@name", "e@example.com", "StrongPass1")
        assert any("underscores" in e.lower() for e in errors)

    def test_missing_email(self):
        """Should report missing email."""
        errors = AuthService._validate_registration("validuser", "", "StrongPass1")
        assert any("email" in e.lower() for e in errors)

    def test_invalid_email(self):
        """Should report invalid email format."""
        errors = AuthService._validate_registration("validuser", "not-email", "StrongPass1")
        assert any("email" in e.lower() for e in errors)

    def test_short_password(self):
        """Should report password too short."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "Short1")
        assert any("8 characters" in e for e in errors)

    def test_weak_password_no_uppercase(self):
        """Should report missing uppercase in password."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "alllowercase1")
        assert any("uppercase" in e.lower() for e in errors)

    def test_weak_password_no_digit(self):
        """Should report missing digit in password."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "NoDigitPass")
        assert any("digit" in e.lower() for e in errors)

    def test_empty_username(self):
        """Should report empty/short username."""
        errors = AuthService._validate_registration("", "e@example.com", "StrongPass1")
        assert len(errors) > 0

    def test_empty_password(self):
        """Should report empty/short password."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "")
        assert len(errors) > 0


class TestStatsAndUtility:
    """Tests for get_stats and ensure_admin."""

    def test_get_stats_empty(self, auth):
        """Should return zero stats for fresh database."""
        stats = auth.get_stats()
        assert stats["total_users"] == 0
        assert stats["active_users"] == 0
        assert stats["revoked_tokens"] == 0
        assert stats["active_api_keys"] == 0
        assert "jose_available" in stats
        assert "passlib_available" in stats

    def test_get_stats_after_registration(self, auth, registered_user):
        """Should reflect registered user in stats."""
        stats = auth.get_stats()
        assert stats["total_users"] == 1
        assert stats["active_users"] == 1

    def test_ensure_admin_creates_first(self, auth):
        """Should create admin user if none exists."""
        result = auth.ensure_admin("admin", "AdminPass1")
        assert "error" not in result
        assert result.get("initial_password") == "AdminPass1"

    def test_ensure_admin_exists(self, auth, admin_user):
        """Should detect existing admin and not create another."""
        result = auth.ensure_admin("admin", "NewAdminPass1")
        assert "already exists" in result["message"].lower()

    def test_ensure_admin_generates_password(self, auth):
        """Should generate password if none provided."""
        result = auth.ensure_admin("admin")
        assert "error" not in result
        assert "initial_password" in result

    def test_cleanup_revoked_tokens(self, auth):
        """Should clean up expired revoked tokens."""
        count = auth.cleanup_revoked_tokens()
        assert isinstance(count, int)
        assert count >= 0

    def test_role_hierarchy_consistency(self):
        """ROLE_HIERARCHY should have expected roles with increasing levels."""
        assert ROLE_HIERARCHY["viewer"] < ROLE_HIERARCHY["user"]
        assert ROLE_HIERARCHY["user"] < ROLE_HIERARCHY["manager"]
        assert ROLE_HIERARCHY["manager"] < ROLE_HIERARCHY["admin"]

    def test_role_permissions_consistency(self):
        """ROLE_PERMISSIONS should have permissions for all roles in hierarchy."""
        for role in ROLE_HIERARCHY:
            assert role in ROLE_PERMISSIONS

    def test_database_initialization(self, tmp_path):
        """AuthService should properly initialize the database on creation."""
        db_path = str(tmp_path / "init_test.sqlite")
        svc = AuthService(db_path=db_path, secret_key="test")
        stats = svc.get_stats()
        assert isinstance(stats, dict)
        assert "total_users" in stats
