"""
Unit tests for AuthService

Tests JWT/HMAC authentication, user management, RBAC, API key auth
using isolated SQLite databases per test.

Modularized into test_auth_svc_parts/ sub-directory.
"""

# Re-export all test classes from sub-modules for backward compatibility
from .test_auth_svc_parts import *

# Re-export fixtures so they're available when running via this facade
from .test_auth_svc_parts.conftest import auth, registered_user, admin_user
