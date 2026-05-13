"""
Tests for AuthService password management and user registration.
"""

import pytest

from src.core.auth_service import AuthService


class TestPasswordManagement:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_string(self):
        """hash_password should return a non-empty string."""
        hashed = AuthService.hash_password("TestPass123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_different_hashes(self):
        """hash_password should produce different hashes for same password (salt)."""
        h1 = AuthService.hash_password("TestPass123")
        h2 = AuthService.hash_password("TestPass123")
        assert h1 != h2

    def test_verify_password_correct(self):
        """verify_password should return True for correct password."""
        hashed = AuthService.hash_password("MyPassword1")
        assert AuthService.verify_password("MyPassword1", hashed) is True

    def test_verify_password_incorrect(self):
        """verify_password should return False for wrong password."""
        hashed = AuthService.hash_password("MyPassword1")
        assert AuthService.verify_password("WrongPassword1", hashed) is False

    def test_verify_password_empty_password(self):
        """verify_password should return False for empty password."""
        hashed = AuthService.hash_password("MyPassword1")
        assert AuthService.verify_password("", hashed) is False

    def test_verify_password_empty_hash(self):
        """verify_password should return False for empty hash."""
        assert AuthService.verify_password("password", "") is False

    def test_verify_password_none_inputs(self):
        """verify_password should return False for None inputs."""
        assert AuthService.verify_password(None, "hash") is False
        assert AuthService.verify_password("password", None) is False

    def test_verify_password_pbkdf2_format(self):
        """verify_password should handle pbkdf2$ format correctly."""
        hashed = AuthService.hash_password("TestPass123")
        if hashed.startswith("pbkdf2$"):
            assert AuthService.verify_password("TestPass123", hashed) is True

    def test_verify_password_invalid_hash_format(self):
        """verify_password should return False for invalid hash format."""
        assert AuthService.verify_password("password", "invalid$hash$format") is False


class TestUserRegistration:
    """Tests for user registration with validation."""

    def test_register_user_success(self, auth):
        """Should register a new user successfully."""
        result = auth.register_user("newuser", "new@example.com", "StrongPass1")
        assert "error" not in result
        assert result["username"] == "newuser"
        assert result["email"] == "new@example.com"
        assert result["role"] == "user"
        assert "user_id" in result

    def test_register_user_with_custom_role(self, auth):
        """Should register a user with a specific role."""
        result = auth.register_user("manager1", "mgr@example.com", "MgrPass123", "manager")
        assert "error" not in result
        assert result["role"] == "manager"

    def test_register_user_duplicate_username(self, auth, registered_user):
        """Should fail when registering with an existing username."""
        result = auth.register_user("testuser", "other@example.com", "OtherPass1")
        assert "error" in result
        assert "already exists" in result["error"].lower()

    def test_register_user_duplicate_email(self, auth, registered_user):
        """Should fail when registering with an existing email."""
        result = auth.register_user("otheruser", "test@example.com", "OtherPass1")
        assert "error" in result
        assert "already" in result["error"].lower()

    def test_register_user_short_username(self, auth):
        """Should reject usernames shorter than 3 characters."""
        result = auth.register_user("ab", "ab@example.com", "StrongPass1")
        assert "error" in result
        assert "3 characters" in result["error"]

    def test_register_user_long_username(self, auth):
        """Should reject usernames longer than 50 characters."""
        long_name = "a" * 51
        result = auth.register_user(long_name, "long@example.com", "StrongPass1")
        assert "error" in result
        assert "50 characters" in result["error"]

    def test_register_user_invalid_username_chars(self, auth):
        """Should reject usernames with special characters."""
        result = auth.register_user("user name", "user@example.com", "StrongPass1")
        assert "error" in result
        assert "underscores" in result["error"].lower()

    def test_register_user_invalid_email(self, auth):
        """Should reject invalid email formats."""
        result = auth.register_user("validuser", "not-an-email", "StrongPass1")
        assert "error" in result
        assert "email" in result["error"].lower()

    def test_register_user_short_password(self, auth):
        """Should reject passwords shorter than 8 characters."""
        result = auth.register_user("pwuser", "pw@example.com", "Short1")
        assert "error" in result
        assert "8 characters" in result["error"]

    def test_register_user_weak_password(self, auth):
        """Should reject passwords without uppercase, lowercase, and digit."""
        result = auth.register_user("weakuser", "weak@example.com", "alllowercase1")
        assert "error" in result
        assert "uppercase" in result["error"].lower()

    def test_register_user_invalid_role(self, auth):
        """Should reject invalid role values."""
        result = auth.register_user("roleuser", "role@example.com", "StrongPass1", "superadmin")
        assert "error" in result
        assert "Invalid role" in result["error"]

    def test_register_user_empty_inputs(self, auth):
        """Should reject empty username, email, or password."""
        result = auth.register_user("", "e@example.com", "StrongPass1")
        assert "error" in result

        result = auth.register_user("user2", "", "StrongPass1")
        assert "error" in result

        result = auth.register_user("user3", "e3@example.com", "")
        assert "error" in result
