"""
Dispatch Action — DAG node and singleton.

Contains exec_dispatch_action DAG node executor and global instance helpers.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from ._types import DispatchRequest, DispatchResult
from ._mixin_core import ActionDispatcher

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  DAG NODE: DISPATCH_ACTION
# ──────────────────────────────────────────────────────────────

async def exec_dispatch_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """DAG node executor for DISPATCH_ACTION."""
    dispatcher: Optional[ActionDispatcher] = ctx.get("_action_dispatcher")
    if not dispatcher:
        dispatcher = ActionDispatcher()

    actions = ctx.get("dispatch_actions", [])
    if not actions:
        return {"status": "NO_ACTION", "results": []}

    is_dry_run = ctx.get("dry_run", False)
    results = []
    for action in actions:
        request = DispatchRequest(
            action_type=action.get("type", ""),
            config=action.get("config", {}),
            context=action.get("context", {}),
            user_id=ctx.get("user_id", ""),
            tenant_id=ctx.get("tenant_id", ""),
            session_id=ctx.get("session_id", ""),
            request_id=ctx.get("request_id", ""),
            dry_run=is_dry_run,
        )
        result = await dispatcher.dispatch(request)
        results.append({
            "action_id": result.action_id,
            "success": result.success,
            "safety_verdict": result.safety_verdict.value,
            "duration_ms": result.total_duration_ms,
            "dry_run": is_dry_run,
            "error": result.executor_result.error if result.executor_result else "",
        })

    all_success = all(r["success"] for r in results)
    return {
        "status": "SUCCESS" if all_success else "PARTIAL",
        "results": results,
        "total_actions": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "dry_run": is_dry_run,
    }


# ──────────────────────────────────────────────────────────────
#  GLOBAL INSTANCE
# ──────────────────────────────────────────────────────────────

_default_dispatcher: Optional[ActionDispatcher] = None
_dispatcher_lock = threading.Lock()


def get_default_dispatcher() -> ActionDispatcher:
    """Get or create the global ActionDispatcher instance (double-checked locking)."""
    global _default_dispatcher
    if _default_dispatcher is None:
        with _dispatcher_lock:
            if _default_dispatcher is None:
                _default_dispatcher = ActionDispatcher()
    return _default_dispatcher


def reset_dispatcher() -> None:
    """Reset the global dispatcher (for testing)."""
    global _default_dispatcher
    _default_dispatcher = None
