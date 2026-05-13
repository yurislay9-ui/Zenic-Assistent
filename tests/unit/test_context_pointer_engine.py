"""
Unit tests for ContextPointerEngine

Tests vectorized signatures (FunctionSignature, ContextPointer),
SignatureIndex indexing (Python and regex-based), similarity
matching / search, and compact context generation.
"""

import os
import pytest

from src.core.context_pointer_engine import (
    FunctionSignature, ContextPointer, SignatureIndex, CONTEXT_STORE_ROOT,
)


# ============================================================
#  Sample Data (shared with sub-modules)
# ============================================================

SAMPLE_PYTHON_CODE = '''
"""Module for user authentication."""

def login(username: str, password: str) -> bool:
    """Authenticate user with credentials."""
    token = create_token(username)
    if verify_password(password, username):
        return True
    return False

async def logout(session_id: str) -> None:
    """End user session."""
    destroy_session(session_id)

class UserAuth:
    """User authentication handler."""

    def authenticate(self, token: str) -> bool:
        """Validate authentication token."""
        return validate_token(token)
'''

SAMPLE_JS_CODE = '''
function handleClick(event) {
    const target = event.target;
    processClick(target);
}

async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}
'''


# ============================================================
#  Fixtures (shared with sub-modules)
# ============================================================

@pytest.fixture
def signature_index(tmp_path, monkeypatch):
    """Create a SignatureIndex with temporary context store."""
    store_dir = str(tmp_path / "ctx_store")
    monkeypatch.setattr("src.core.context_pointer_engine.CONTEXT_STORE_ROOT", store_dir)
    return SignatureIndex(project_root=str(tmp_path))


@pytest.fixture
def populated_index(signature_index):
    """Create a SignatureIndex with Python code indexed."""
    signature_index.index_code(SAMPLE_PYTHON_CODE, "auth.py")
    return signature_index


from .test_ctx_ptr_parts import *  # noqa: F401,F403
