"""
test_auth_svc_parts — sub-modules for test_auth_service.py

Re-exports all test classes for backward compatibility.
"""

from .test_password_and_registration import *
from .test_login_and_tokens import *
from .test_user_crud_rbac import *
from .test_api_keys_and_stats import *
