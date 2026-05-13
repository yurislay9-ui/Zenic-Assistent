"""
Tests for AuthService user CRUD and RBAC.
"""

import pytest


class TestUserCRUD:
    """Tests for user management operations."""

    def test_get_user(self, auth, registered_user):
        """Should retrieve a user by ID without password hash."""
        uid = registered_user["user_id"]
        user = auth.get_user(uid)
        assert user is not None
        assert user["username"] == "testuser"
        assert "password_hash" not in user

    def test_get_user_nonexistent(self, auth):
        """Should return None for non-existent user ID."""
        user = auth.get_user(99999)
        assert user is None

    def test_update_user_email(self, auth, registered_user):
        """Should update user email."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, email="newemail@example.com")
        assert "error" not in result
        assert result["email"] == "newemail@example.com"

    def test_update_user_role(self, auth, registered_user):
        """Should update user role."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, role="manager")
        assert "error" not in result
        assert result["role"] == "manager"

    def test_update_user_invalid_role(self, auth, registered_user):
        """Should reject invalid role update."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, role="superadmin")
        assert "error" in result
        assert "Invalid role" in result["error"]

    def test_update_user_no_valid_fields(self, auth, registered_user):
        """Should reject updates with no valid fields."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, invalid_field="value")
        assert "error" in result

    def test_update_nonexistent_user(self, auth):
        """Should return error for non-existent user update."""
        result = auth.update_user(99999, email="x@example.com")
        assert "error" in result

    def test_deactivate_user(self, auth, registered_user):
        """Should deactivate a user."""
        uid = registered_user["user_id"]
        assert auth.deactivate_user(uid) is True
        user = auth.get_user(uid)
        assert user["active"] == 0

    def test_deactivate_nonexistent_user(self, auth):
        """Should return False for non-existent user deactivation."""
        assert auth.deactivate_user(99999) is False

    def test_list_users(self, auth, registered_user):
        """Should list registered users."""
        users = auth.list_users()
        assert isinstance(users, list)
        assert len(users) >= 1

    def test_list_users_by_role(self, auth, admin_user, registered_user):
        """Should filter users by role."""
        admins = auth.list_users(role="admin")
        assert all(u["role"] == "admin" for u in admins)

    def test_change_password(self, auth, registered_user):
        """Should change password with correct old password."""
        uid = registered_user["user_id"]
        assert auth.change_password(uid, "StrongPass1", "NewStrong1") is True
        result = auth.login_user("testuser", "NewStrong1")
        assert "error" not in result

    def test_change_password_wrong_old(self, auth, registered_user):
        """Should fail with wrong old password."""
        uid = registered_user["user_id"]
        assert auth.change_password(uid, "WrongOld1", "NewStrong1") is False

    def test_reset_password(self, auth, registered_user):
        """Should reset password without old password (admin op)."""
        uid = registered_user["user_id"]
        assert auth.reset_password(uid, "ResetPass1") is True
        result = auth.login_user("testuser", "ResetPass1")
        assert "error" not in result


class TestRBAC:
    """Tests for Role-Based Access Control."""

    def test_check_permission_admin(self, auth, admin_user):
        """Admin should have manage_users permission."""
        uid = admin_user["user_id"]
        assert auth.check_permission(uid, "manage_users") is True

    def test_check_permission_user_read(self, auth, registered_user):
        """Regular user should have read permission."""
        uid = registered_user["user_id"]
        assert auth.check_permission(uid, "read") is True

    def test_check_permission_user_no_manage(self, auth, registered_user):
        """Regular user should NOT have manage_users permission."""
        uid = registered_user["user_id"]
        assert auth.check_permission(uid, "manage_users") is False

    def test_check_role_admin_meets_user(self, auth, admin_user):
        """Admin role should meet minimum 'user' role requirement."""
        uid = admin_user["user_id"]
        assert auth.check_role(uid, "user") is True

    def test_check_role_user_not_meet_admin(self, auth, registered_user):
        """User role should NOT meet minimum 'admin' role requirement."""
        uid = registered_user["user_id"]
        assert auth.check_role(uid, "admin") is False

    def test_check_role_deactivated_user(self, auth, registered_user):
        """Deactivated user should fail role check."""
        uid = registered_user["user_id"]
        auth.deactivate_user(uid)
        assert auth.check_role(uid, "user") is False

    def test_check_role_nonexistent_user(self, auth):
        """Non-existent user should fail role check."""
        assert auth.check_role(99999, "user") is False

    def test_get_user_permissions(self, auth, admin_user):
        """Should return correct permissions for admin role."""
        uid = admin_user["user_id"]
        perms = auth.get_user_permissions(uid)
        assert "manage_users" in perms
        assert "read" in perms

    def test_get_user_permissions_viewer(self, auth):
        """Viewer role should only have read permission."""
        result = auth.register_user("viewer1", "viewer@example.com", "ViewerPass1", "viewer")
        uid = result["user_id"]
        perms = auth.get_user_permissions(uid)
        assert perms == {"read"}
