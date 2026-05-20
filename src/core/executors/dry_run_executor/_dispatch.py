"""
Dry-Run Executor — Dispatch function and singleton.

Contains dry_run_dispatch and singleton helpers.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ._types import DryRunOperation, DryRunResult
from ._mixin_core import DryRunExecutor

logger = logging.getLogger(__name__)


def dry_run_dispatch(
    dispatcher: Any,
    request: Any,
) -> DryRunResult:
    """Run a dispatch through DryRunExecutor and return a DryRunResult.

    This function intercepts the full dispatch pipeline, recording
    what *would* happen without executing anything for real.

    Args:
        dispatcher: An ActionDispatcher instance (or compatible object)
            with a ``dispatch`` method.
        request: A DispatchRequest instance (or dict) describing
            the action to simulate.

    Returns:
        A DryRunResult with all simulated operations, impact preview,
        estimated effects, and a predicted safety verdict.
    """
    executor = get_dry_run_executor()

    # Normalise request to dict for consistent handling
    if hasattr(request, "__dataclass_fields__"):
        request_dict = asdict(request)
    elif isinstance(request, dict):
        request_dict = dict(request)
    else:
        request_dict = {"raw": str(request)}

    action_type = request_dict.get("action_type", "unknown")
    config = request_dict.get("config", {})
    context = request_dict.get("context", {})

    # ── 1. Get impact preview ────────────────────────────────
    impact_preview_dict: Dict[str, Any] = {}
    try:
        impact_preview_dict = executor.preview_action(
            action_type, config, context,
        )
    except Exception as exc:
        logger.warning("dry_run_dispatch: impact preview failed: %s", exc)
        impact_preview_dict = {"error": str(exc)}

    # ── 2. Simulate the action ───────────────────────────────
    simulated_ops: List[DryRunOperation] = []
    would_succeed = True

    try:
        action_lower = action_type.lower()
        if action_lower in ("email", "send_email"):
            executor._intercept_smtp(config)
        elif action_lower in ("http", "http_request"):
            executor._intercept_http(config)
        elif action_lower in ("database", "db", "database_operation"):
            executor._intercept_db(config)
        elif action_lower in ("file", "file_operation"):
            executor._intercept_file(config)
        else:
            executor._record_operation(
                operation_type=action_lower,
                target=config.get("operation", action_type),
                would_affect={"intercepted": True},
            )

        simulated_ops = list(executor.operations)
    except Exception as exc:
        logger.warning("dry_run_dispatch: simulation failed: %s", exc)
        would_succeed = False

    # ── 3. Estimate effects ──────────────────────────────────
    estimated_effects: Dict[str, Any] = {
        "operations_count": len(simulated_ops),
        "types": executor.summary(),
    }

    # ── 4. Predict safety verdict ────────────────────────────
    risk_level = impact_preview_dict.get("risk_level", "none")
    risk_score = impact_preview_dict.get("risk_score", 0.0)

    if risk_level in ("critical", "high") or risk_score >= 0.8:
        safety_verdict = "DENY"
        would_succeed = False
    elif risk_level == "medium" or risk_score >= 0.5:
        safety_verdict = "CONFIRM"
    else:
        safety_verdict = "ALLOW"

    result = DryRunResult(
        original_request=request_dict,
        simulated_operations=simulated_ops,
        impact_preview=impact_preview_dict,
        estimated_effects=estimated_effects,
        would_succeed=would_succeed,
        safety_verdict_would_be=safety_verdict,
    )

    logger.info(
        "dry_run_dispatch: %s — would_succeed=%s verdict=%s ops=%d",
        action_type, would_succeed, safety_verdict, len(simulated_ops),
    )

    return result


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_instance: Optional[DryRunExecutor] = None
_instance_lock = threading.Lock()


def get_dry_run_executor() -> DryRunExecutor:
    """Return the singleton DryRunExecutor instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DryRunExecutor()
    return _instance


def reset_dry_run_executor() -> None:
    """Reset the singleton instance (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
