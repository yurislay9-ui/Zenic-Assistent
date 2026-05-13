"""
ZENIC-AGENTS - ActionExecutor Unit Tests

Tests for src/core/action_executor.py:
  - ActionResult data class
  - Utility validators (_validate_email, _validate_url, _safe_path, _validate_sql)
  - EmailExecutor (dry-run mode, validation)
  - HttpExecutor (validation, invalid inputs)
  - DatabaseExecutor (query, script operations)
  - FileExecutor (write/read/mkdir operations)
  - TransformExecutor (map_fields, filter, sort, aggregate)
  - WebhookExecutor (verify signature)
  - NotificationExecutor (log channel, fallbacks)

Modularized into test_action_exec_parts/ sub-directory.
"""

# Re-export all test classes from sub-modules for backward compatibility
from .test_action_exec_parts import *

# Re-export run_async helper and fixtures so they're available when running via this facade
from .test_action_exec_parts.conftest import run_async
