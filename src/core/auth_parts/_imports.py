"""
Shared imports and constants for auth_parts sub-modules.
"""

import os
import re
import json
import time
import hashlib
import hmac
import secrets
import sqlite3
import threading
import logging
import base64
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Set, Callable, Any

logger = logging.getLogger(__name__)

# --- Optional deps ---
try:
    from jose import JWTError, jwt as jose_jwt
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False; jose_jwt = None; JWTError = Exception

try:
    from passlib.context import CryptContext
    PASSLIB_AVAILABLE = True
    # Truncate passwords to 72 bytes (bcrypt limit) to avoid ValueError
    # on newer passlib/bcrypt versions that enforce this strictly
    _pwd_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=12,
        bcrypt__ident="2b",
    )
    # Verify the bcrypt backend actually works (bcrypt 4.1+ / 5.x
    # changed the API and passlib may not be fully compatible)
    _pwd_context.hash("test")
except ImportError:
    PASSLIB_AVAILABLE = False; _pwd_context = None
except Exception:
    # Fallback if bcrypt backend has compatibility issues
    # (e.g. bcrypt.__about__ removed in 4.1+, 72-byte enforcement, etc.)
    PASSLIB_AVAILABLE = False; _pwd_context = None
    try:
        import bcrypt as _bc
        _bv = getattr(_bc, '__version__', '?')
    except ImportError:
        _bv = 'not installed'
    logger.warning(
        "passlib/bcrypt unavailable (bcrypt %s incompatible with passlib 1.7.4), "
        "using PBKDF2-SHA256 fallback. Fix: pip install 'bcrypt>=4.0.0,<4.1.0'",
        _bv,
    )

try:
    from fastapi import Depends, HTTPException, status
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    HAS_FASTAPI = True
    _security = HTTPBearer()
except ImportError:
    HAS_FASTAPI = False; Depends = None; HTTPException = None
    status = None; _security = None

# --- Constants ---
# ── Phase 6: Granular Multi-Role System ─────────────────────
# Roles: admin (owner), gerente (manager), operador (operator), viewer (read-only)
# Each role has fine-grained per-action permissions.

ROLE_HIERARCHY: Dict[str, int] = {
    "viewer": 0,
    "operador": 1,
    "gerente": 2,
    "admin": 3,
    # Backward-compatible aliases
    "user": 1,
    "manager": 2,
}

# Per-action granular permissions
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {
        # Read
        "read", "view_analytics", "view_audit",
        # Write
        "write", "create_invoice", "create_order", "create_client",
        "send_email", "send_notification",
        # Delete
        "delete", "delete_record",
        # Management
        "manage_users", "manage_roles", "manage_system",
        "manage_blueprints", "manage_sna",
        # Financial
        "approve_financial", "create_payment", "refund",
        # Approval
        "approve_action", "approve_destructive",
        # Config
        "change_config", "export_data", "import_data",
    },
    "gerente": {
        # Read
        "read", "view_analytics", "view_audit",
        # Write
        "write", "create_invoice", "create_order", "create_client",
        "send_email", "send_notification",
        # Delete
        "delete", "delete_record",
        # Financial
        "approve_financial", "create_payment",
        # Approval
        "approve_action",
        # Config
        "export_data",
    },
    "operador": {
        # Read
        "read", "view_analytics",
        # Write
        "write", "create_invoice", "create_order", "create_client",
        "send_email", "send_notification",
    },
    "viewer": {
        "read", "view_analytics",
    },
    # Backward-compatible aliases
    "user": {
        "read", "write", "create_invoice", "create_order", "create_client",
        "send_email", "send_notification",
    },
    "manager": {
        "read", "write", "delete", "view_analytics", "view_audit",
        "approve_financial", "approve_action", "create_payment",
        "send_email", "send_notification", "export_data",
    },
}

# Actions that require specific permissions
ACTION_PERMISSION_MAP: Dict[str, str] = {
    "create_invoice": "create_invoice",
    "create_order": "create_order",
    "create_client": "create_client",
    "create_payment": "create_payment",
    "send_email": "send_email",
    "send_notification": "send_notification",
    "delete_record": "delete_record",
    "approve_financial": "approve_financial",
    "approve_action": "approve_action",
    "approve_destructive": "approve_destructive",
    "refund": "refund",
    "change_config": "change_config",
    "export_data": "export_data",
    "import_data": "import_data",
    "manage_users": "manage_users",
    "manage_roles": "manage_roles",
    "manage_system": "manage_system",
    "manage_blueprints": "manage_blueprints",
    "manage_sna": "manage_sna",
    "view_audit": "view_audit",
}

ACCESS_EXPIRE_MIN = 60
REFRESH_EXPIRE_DAYS = 7
PBKDF2_ITERATIONS = 100_000
API_KEY_PREFIX = "zenic_"
PAGE_SIZE = 50
