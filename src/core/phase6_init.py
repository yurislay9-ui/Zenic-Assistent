"""
Zenic-Agents Asistente - Phase 6 Integration Wiring

Connects all Phase 6 components into the existing system:
- SafetyGate → ApprovalChain → WorkflowEngine
- LicenseManager → DegradedModeManager
- DefenseManager → DegradedModeManager
- DegradedModeManager → SafetyGate (enforcement)
- AuthService RBAC → ApprovalChain (role-based approval)

This module provides the `initialize_phase6()` function that
should be called during application startup to wire everything.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def initialize_phase6(start_defense_monitoring: bool = True) -> Dict[str, Any]:
    """Initialize all Phase 6 components and wire them together.

    Call this during application startup, after AuthService is initialized.

    Args:
        start_defense_monitoring: Whether to start background defense monitoring.

    Returns:
        Dict with initialization status for each component.
    """
    results: Dict[str, Any] = {}

    # ── 1. Degraded Mode Manager ──────────────────────────
    try:
        from src.core.degraded_mode.manager import get_degraded_mode_manager, SystemMode
        dm = get_degraded_mode_manager()
        results["degraded_mode"] = {"status": "ok", "mode": dm.get_current_mode().value}
        logger.info("Phase6: DegradedModeManager initialized (mode=%s)", dm.get_current_mode().value)
    except Exception as exc:
        results["degraded_mode"] = {"status": "error", "error": str(exc)}
        logger.error("Phase6: DegradedModeManager init failed: %s", exc)

    # ── 2. License Manager ────────────────────────────────
    try:
        from src.core.license.manager import get_license_manager
        lm = get_license_manager()
        results["license"] = {"status": "ok", "data": lm.get_status()}

        # Wire license events to degraded mode
        try:
            from src.core.degraded_mode.manager import get_degraded_mode_manager, SystemMode
            from src.core.license.types import LicenseStatus

            dm = get_degraded_mode_manager()

            def _on_license_event(event_type: str, data: Dict[str, Any]) -> None:
                """React to license events by adjusting operating mode."""
                if event_type == "kill_switch_activated":
                    dm.enter_paralysis(level=3, reason=f"Kill switch: {data.get('reason', '')}")
                elif event_type == "kill_switch_deactivated":
                    # Only return to normal if license is valid
                    result = lm.verify()
                    if result.valid:
                        dm.return_to_normal(reason="Kill switch deactivated, license valid")

            lm.on_license_event(_on_license_event)
            logger.info("Phase6: License → DegradedMode wired")
        except Exception as exc:
            logger.warning("Phase6: License-DegradedMode wiring failed: %s", exc)

    except Exception as exc:
        results["license"] = {"status": "error", "error": str(exc)}
        logger.error("Phase6: LicenseManager init failed: %s", exc)

    # ── 3. Defense Manager ────────────────────────────────
    try:
        from src.core.defense import get_defense_manager
        defense = get_defense_manager()
        defense.initialize_all(start_monitoring=start_defense_monitoring)
        results["defense"] = {"status": "ok", "active_layers": defense.get_status().active_layers}
        logger.info("Phase6: DefenseManager initialized (%d active layers)", defense.get_status().active_layers)
    except Exception as exc:
        results["defense"] = {"status": "error", "error": str(exc)}
        logger.error("Phase6: DefenseManager init failed: %s", exc)

    # ── 4. Approval Chain ─────────────────────────────────
    try:
        from src.core.approval.chain import get_approval_chain
        from src.core.approval.workflows import get_workflow_engine

        chain = get_approval_chain()
        engine = get_workflow_engine()
        results["approval"] = {
            "status": "ok",
            "workflows": len(engine.list_workflows()),
        }
        logger.info("Phase6: ApprovalChain + WorkflowEngine initialized")
    except Exception as exc:
        results["approval"] = {"status": "error", "error": str(exc)}
        logger.error("Phase6: ApprovalChain init failed: %s", exc)

    # ── 5. Wire SafetyGate → ApprovalChain ────────────────
    try:
        from src.core.executors.safety_gate import get_default_safety_gate, SafetyVerdict
        from src.core.approval.chain import get_approval_chain

        safety_gate = get_default_safety_gate()
        chain = get_approval_chain()

        # Store original check method
        _original_check = safety_gate.check

        def _enhanced_check(
            action_type: str, config: Dict[str, Any],
            context: Optional[Dict[str, Any]] = None,
        ) -> Any:
            """Enhanced SafetyGate check that integrates with ApprovalChain.

            When SafetyGate returns APPROVE, automatically creates an
            approval request in the chain.
            """
            result = _original_check(action_type, config, context)

            # Check degraded mode before proceeding
            try:
                from src.core.degraded_mode.manager import get_degraded_mode_manager
                dm = get_degraded_mode_manager()
                action_check = dm.check_action(action_type)
                if not action_check["allowed"]:
                    from src.core.executors.safety_gate import SafetyCheckResult, SafetyVerdict, ActionCategory
                    return SafetyCheckResult(
                        verdict=SafetyVerdict.DENY,
                        category=ActionCategory.SYSTEM,
                        reason=action_check["reason"],
                        rule_name="degraded_mode_block",
                    )
            except ImportError:
                pass

            # If APPROVE, create approval request
            if result.verdict == SafetyVerdict.APPROVE:
                try:
                    requested_by = 0
                    if context and "user_id" in context:
                        requested_by = context["user_id"]

                    chain.create_request(
                        action_type=action_type,
                        action_config=config,
                        requested_by=requested_by,
                        required_role="gerente",
                    )
                except Exception as exc:
                    logger.warning("Phase6: Auto-approval request creation failed: %s", exc)

            return result

        # Monkey-patch the enhanced check
        safety_gate.check = _enhanced_check
        results["safety_gate_wiring"] = {"status": "ok"}
        logger.info("Phase6: SafetyGate → ApprovalChain wired")
    except Exception as exc:
        results["safety_gate_wiring"] = {"status": "error", "error": str(exc)}
        logger.warning("Phase6: SafetyGate wiring failed: %s", exc)

    # ── 6. Auto-create default license if none exists ──────
    try:
        from src.core.license.manager import get_license_manager, LicenseTier
        lm = get_license_manager()
        if not lm.get_current_license():
            # Create a free-tier license by default
            lm.create_license(
                tier=LicenseTier.FREE,
                issued_to="Zenic-Agents Default",
                features=["basic_pipeline", "chat_completions"],
                max_users=1,
                expires_days=0,  # Perpetual free license
            )
            logger.info("Phase6: Default free license created")
    except Exception as exc:
        logger.warning("Phase6: Default license creation failed: %s", exc)

    # ── Summary ────────────────────────────────────────────
    ok_count = sum(1 for v in results.values() if v.get("status") == "ok")
    total = len(results)
    logger.info("Phase6: Initialization complete (%d/%d components OK)", ok_count, total)
    return results


def get_phase6_status() -> Dict[str, Any]:
    """Get comprehensive Phase 6 status across all components."""
    status: Dict[str, Any] = {}

    try:
        from src.core.degraded_mode.manager import get_degraded_mode_manager
        status["degraded_mode"] = get_degraded_mode_manager().get_status()
    except Exception:
        status["degraded_mode"] = {"error": "unavailable"}

    try:
        from src.core.license.manager import get_license_manager
        status["license"] = get_license_manager().get_status()
    except Exception:
        status["license"] = {"error": "unavailable"}

    try:
        from src.core.defense import get_defense_manager
        ds = get_defense_manager().get_status()
        status["defense"] = {
            "score": ds.overall_score,
            "active_layers": ds.active_layers,
            "recommendations": ds.recommendations,
        }
    except Exception:
        status["defense"] = {"error": "unavailable"}

    try:
        from src.core.approval.chain import get_approval_chain
        status["approval"] = get_approval_chain().get_stats()
    except Exception:
        status["approval"] = {"error": "unavailable"}

    return status


__all__ = ["initialize_phase6", "get_phase6_status"]
