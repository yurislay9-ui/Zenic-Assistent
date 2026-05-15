"""
Shared fixtures for test_auth_svc_parts sub-modules.
"""

import pytest

# auth_parts removed — AuthService is now a stub
from src.core.auth_service import AuthService, ROLE_HIERARCHY, ROLE_PERMISSIONS


@pytest.fixture
def auth(tmp_path):
    """Create an AuthService with a temp SQLite database."""
    db_path = str(tmp_path / "test_auth.sqlite")
    return AuthService(db_path=db_path, secret_key="test-secret-key-for-unit-tests")


@pytest.fixture
def registered_user(auth):
    """Register a standard user and return the result dict."""
    return auth.register_user("testuser", "test@example.com", "StrongPass1", "user")


@pytest.fixture
def admin_user(auth):
    """Register an admin user and return the result dict."""
    return auth.register_user("adminuser", "admin@example.com", "AdminPass1", "admin")
