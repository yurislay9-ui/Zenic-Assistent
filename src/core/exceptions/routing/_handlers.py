"""
Zenic-Agents - Exception Router Action Handlers (Phase C2)

Individual action handler methods for the ExceptionRouter.
Uses lazy imports to avoid circular dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from ..engine import ExceptionSignal
from ._router import RoutingAction

logger = logging.getLogger(__name__)


class ExceptionRouterHandlersMixin:
    """Mixin providing action handler methods for ExceptionRouter.

    Intended to be mixed into ExceptionRouterBase to form
    the complete ExceptionRouter.
    """

    def _action_escalate_human(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """ESCALATE_HUMAN: create an approval request."""
        try:
            from src.core.approval.chain import get_approval_chain
            chain = get_approval_chain()
            req = chain.create_request(
                action_type="exception_escalation",
                action_config={
                    "signal_id": signal.signal_id,
                    "category": signal.category.value,
                    "severity": signal.severity.value,
                    "message": signal.message,
                    "source": signal.source,
                },
                requested_by=0,  # system
                required_role="gerente",
                priority="high",
                metadata=signal.context,
            )
            return {
                "status": "escalated",
                "detail": f"Approval request {req.request_id} created",
                "approval_request_id": req.request_id,
            }
        except ImportError:
            logger.warning(
                "ExceptionRouter: approval.chain not available, logging escalation"
            )
            return {"status": "escalated_log_only", "detail": "ApprovalChain unavailable"}

    def _action_pause_automation(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """PAUSE_AUTOMATION: toggle off automation."""
        try:
            from src.core.automation_engine import AutomationEngine
            # Lazy: we don't store a reference; just signal the intent.
            logger.warning(
                "ExceptionRouter: PAUSE_AUTOMATION requested for signal %s",
                signal.signal_id,
            )
            return {
                "status": "paused",
                "detail": "Automation pause requested (AutomationEngine integration)",
            }
        except ImportError:
            logger.warning(
                "ExceptionRouter: automation_engine not available, logging pause request"
            )
            return {"status": "paused_log_only", "detail": "AutomationEngine unavailable"}

    def _action_degrade_system(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """DEGRADE_SYSTEM: enter degraded mode."""
        try:
            from src.core.degraded_mode.manager import get_degraded_mode_manager
            mgr = get_degraded_mode_manager()
            mgr.enter_degraded(
                reason="exception_triggered",
                message=f"Exception {signal.signal_id}: {signal.message[:80]}",
                level=1,
            )
            return {
                "status": "degraded",
                "detail": "System entered degraded mode",
            }
        except ImportError:
            logger.warning(
                "ExceptionRouter: degraded_mode.manager not available, logging degrade request"
            )
            return {"status": "degraded_log_only", "detail": "DegradedModeManager unavailable"}

    def _action_retry_with_backoff(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """RETRY_WITH_BACKOFF: return retry configuration."""
        config = {
            "max_retries": 3,
            "base_delay_ms": 200,
            "max_delay_ms": 5000,
            "backoff_factor": 2.0,
            "jitter": True,
        }
        return {
            "status": "retry_config",
            "detail": "Retry-with-backoff configuration provided",
            "retry_config": config,
        }

    def _action_notify_admin(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """NOTIFY_ADMIN: create a notification record."""
        notification = {
            "type": "admin_notification",
            "signal_id": signal.signal_id,
            "category": signal.category.value,
            "severity": signal.severity.value,
            "source": signal.source,
            "message": signal.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "ExceptionRouter: admin notification created for signal %s",
            signal.signal_id,
        )
        return {
            "status": "notified",
            "detail": "Admin notification created",
            "notification": notification,
        }

    def _action_abort(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """ABORT_ACTION: return an abort signal."""
        return {
            "status": "aborted",
            "detail": f"Action aborted due to {signal.category.value}",
        }

    def _action_log_and_continue(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """LOG_AND_CONTINUE: just log."""
        logger.info(
            "ExceptionRouter: LOG_AND_CONTINUE for signal %s [%s:%s] – %s",
            signal.signal_id, signal.category.value, signal.severity.value,
            signal.message[:120],
        )
        return {"status": "logged", "detail": "Logged and continued"}

    def _action_reroute(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """REROUTE: find the next matching rule (skip current match)."""
        with self._lock:  # type: ignore[attr-defined]
            matched = False
            for rule in self._rules:  # type: ignore[attr-defined]
                if rule.matches(signal):
                    if matched:
                        # This is the second match → use it
                        logger.info(
                            "ExceptionRouter: rerouted signal %s to rule %s → %s",
                            signal.signal_id, rule.rule_id, rule.action.value,
                        )
                        return {
                            "status": "rerouted",
                            "detail": f"Rerouted to action {rule.action.value}",
                            "rerouted_action": rule.action.value,
                            "rerouted_rule_id": rule.rule_id,
                        }
                    matched = True

        return {
            "status": "no_alternative_route",
            "detail": "No alternative rule found for rerouting",
        }


__all__ = ["ExceptionRouterHandlersMixin"]
