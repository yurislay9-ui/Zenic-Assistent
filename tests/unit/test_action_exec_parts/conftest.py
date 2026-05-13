"""
Shared fixtures for test_action_exec_parts sub-modules.
"""

import asyncio
import pytest

from src.core.action_executor import (
    ActionResult,
    ActionExecutor,
    EmailExecutor,
    HttpExecutor,
    DatabaseExecutor,
    FileExecutor,
    TransformExecutor,
    WebhookExecutor,
    NotificationExecutor,
    _validate_email,
    _validate_url,
    _safe_path,
    _validate_sql,
)


def run_async(coro):
    """Helper to run an async coroutine in sync test context."""
    return asyncio.run(coro)
