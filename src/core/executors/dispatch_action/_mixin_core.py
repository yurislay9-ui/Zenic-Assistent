"""Dispatch Action — ActionDispatcher class.

Main dispatcher: Blueprint → Policy → Safety Gate → Executor → Audit.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ..base import ActionResult, ActionExecutor, ExecutorRegistry, get_default_registry
from ..safety_gate import SafetyGate, SafetyVerdict, SafetyCheckResult, get_default_safety_gate
from ..audit_logger import ExecutorAuditLogger, AuditEntry, get_default_audit_logger
from ..blueprint_schema import Blueprint, BlueprintValidator, get_default_blueprint
from ..dispatch_parts import BlueprintBridgeMixin
from ..impact_preview import ImpactPreviewEngine, get_impact_preview_engine
from ..policy_engine import PolicyEngine, PolicyDecision, get_policy_engine
from ..db_journal import DBTransactionJournal, get_db_journal
from ..coordinated_rollback import CoordinatedRollbackManager, get_coordinated_rollback_manager
from ._types import DispatchRequest, DispatchResult

logger = logging.getLogger(__name__)


class ActionDispatcher(BlueprintBridgeMixin):
    """Main dispatcher that routes actions through the full pipeline.

    Pipeline stages:
      1. Blueprint validation (schema check)
      2. Safety Gate (deterministic validation)
      3. Confirmation/Approval check (if required)
      4. Executor execution (or dry-run simulation)
      5. Audit logging
      6. Result return

    INVARIANT: Safety Gate DENY is absolute — no override possible.

    Phase 5: Inherits BlueprintBridgeMixin for dynamic Blueprint
    switching from the Blueprint Registry.

    Phase C1: Supports dry_run=True in DispatchRequest to simulate
    execution without real I/O side effects.
    """

    def __init__(
        self,
        registry: Optional[ExecutorRegistry] = None,
        safety_gate: Optional[SafetyGate] = None,
        audit_logger: Optional[ExecutorAuditLogger] = None,
        blueprint: Optional[Blueprint] = None,
    ) -> None:
        self._registry = registry or get_default_registry()
        self._safety_gate = safety_gate or get_default_safety_gate()
        self._audit_logger = audit_logger or get_default_audit_logger()
        self._blueprint = blueprint or get_default_blueprint()
        self._pending_confirmations: Dict[str, DispatchRequest] = {}
        self._pending_approvals: Dict[str, DispatchRequest] = {}
        self._impact_preview: Optional[ImpactPreviewEngine] = None
        self._policy_engine: Optional[PolicyEngine] = None
        self._db_journal: Optional[DBTransactionJournal] = None
        self._coordinated_rollback: Optional[CoordinatedRollbackManager] = None
        self._stats = {
            "dispatched": 0,
            "succeeded": 0,
            "failed": 0,
            "safety_denied": 0,
            "safety_confirmed": 0,
            "safety_approved": 0,
            "rate_limited": 0,
            "dry_run_executed": 0,
        }

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        """Dispatch an action through the full pipeline."""
        start = time.monotonic()
        stages: Dict[str, float] = {}

        # Phase 5: Auto-load Blueprint from registry
        if request.blueprint_name:
            self.set_blueprint_from_registry(
                blueprint_name=request.blueprint_name,
                tenant_id=request.tenant_id,
            )

        self._stats["dispatched"] += 1

        # ── Stage 1: Blueprint Validation ──
        bp_start = time.monotonic()
        blueprint_errors = self._validate_blueprint(request)
        stages["blueprint_validation"] = (time.monotonic() - bp_start) * 1000

        if blueprint_errors:
            logger.warning(
                "ActionDispatcher: Blueprint validation failed for %s: %s",
                request.action_type, blueprint_errors,
            )
            critical_errors = [e for e in blueprint_errors if "required" in e.lower() or "invalid type" in e.lower()]
            if critical_errors:
                self._stats["failed"] += 1
                return DispatchResult(
                    action_id=request.action_id, success=False,
                    safety_verdict=SafetyVerdict.DENY,
                    blueprint_errors=blueprint_errors,
                    total_duration_ms=(time.monotonic() - start) * 1000,
                    pipeline_stages=stages,
                )

        # ── Stage 1.5: Policy Engine ──
        policy_start = time.monotonic()
        policy_decision = self.evaluate_policies(request)
        stages["policy_engine"] = (time.monotonic() - policy_start) * 1000

        if not policy_decision.allowed:
            self._stats["safety_denied"] += 1
            self._stats["failed"] += 1
            return DispatchResult(
                action_id=request.action_id, success=False,
                safety_verdict=SafetyVerdict.DENY,
                blueprint_errors=blueprint_errors,
                total_duration_ms=(time.monotonic() - start) * 1000,
                pipeline_stages=stages,
            )

        # ── Stage 2: Safety Gate ──
        safety_result = self._run_safety_gate(request, stages)
        if safety_result is not None and safety_result.verdict in (
            SafetyVerdict.DENY, SafetyVerdict.RATE_LIMITED,
            SafetyVerdict.CONFIRM, SafetyVerdict.APPROVE,
        ):
            blocked = self._check_blocking_verdict(
                request, safety_result, blueprint_errors, stages, start,
            )
            if blocked is not None:
                return blocked

        # ── Stage 3: Execute Action (or dry-run) ──
        exec_start = time.monotonic()
        if request.dry_run:
            executor_result = await self._dry_run_execute(request)
            stages["dry_run_executor"] = (time.monotonic() - exec_start) * 1000
            self._stats["dry_run_executed"] += 1
        else:
            executor_result = await self._registry.execute_action(
                request.action_type, request.config, request.context,
            )
            stages["executor"] = (time.monotonic() - exec_start) * 1000

        # ── Stage 4: Audit Log (skip in dry-run mode) ──
        if not request.dry_run:
            self._log_audit(request, executor_result, safety_result, stages)
        else:
            logger.info(
                "ActionDispatcher: Dry-run completed for %s (action_id=%s)",
                request.action_type, request.action_id,
            )

        # ── Finalize ──
        if executor_result.success:
            self._stats["succeeded"] += 1
        else:
            self._stats["failed"] += 1

        return DispatchResult(
            action_id=request.action_id,
            success=executor_result.success,
            safety_verdict=safety_result.verdict if safety_result else SafetyVerdict.ALLOW,
            executor_result=executor_result,
            safety_result=safety_result,
            blueprint_errors=blueprint_errors,
            total_duration_ms=(time.monotonic() - start) * 1000,
            pipeline_stages=stages,
        )

    # ── Safety Gate Helper ────────────────────────────────

    def _run_safety_gate(
        self, request: DispatchRequest, stages: Dict[str, float],
    ) -> Optional[SafetyCheckResult]:
        """Run Safety Gate check on the request."""
        sg_start = time.monotonic()
        result = self._safety_gate.check(
            request.action_type, request.config, request.context,
        )
        stages["safety_gate"] = (time.monotonic() - sg_start) * 1000
        return result

    def _check_blocking_verdict(
        self,
        request: DispatchRequest,
        safety_result: SafetyCheckResult,
        blueprint_errors: List[str],
        stages: Dict[str, float],
        start: float,
    ) -> Optional[DispatchResult]:
        """Check if a safety verdict blocks execution."""
        verdict = safety_result.verdict

        if verdict == SafetyVerdict.DENY:
            self._stats["safety_denied"] += 1
            self._stats["failed"] += 1
            return DispatchResult(
                action_id=request.action_id, success=False,
                safety_verdict=verdict, safety_result=safety_result,
                blueprint_errors=blueprint_errors,
                total_duration_ms=(time.monotonic() - start) * 1000,
                pipeline_stages=stages,
            )

        if verdict == SafetyVerdict.RATE_LIMITED:
            self._stats["rate_limited"] += 1
            return DispatchResult(
                action_id=request.action_id, success=False,
                safety_verdict=verdict, safety_result=safety_result,
                blueprint_errors=blueprint_errors,
                total_duration_ms=(time.monotonic() - start) * 1000,
                pipeline_stages=stages,
            )

        if verdict == SafetyVerdict.CONFIRM:
            if not self._safety_gate.is_confirmed(request.action_id):
                self._pending_confirmations[request.action_id] = request
                self._stats["safety_confirmed"] += 1
                return DispatchResult(
                    action_id=request.action_id, success=False,
                    safety_verdict=verdict, safety_result=safety_result,
                    blueprint_errors=blueprint_errors,
                    total_duration_ms=(time.monotonic() - start) * 1000,
                    pipeline_stages=stages,
                )

        if verdict == SafetyVerdict.APPROVE:
            if not self._safety_gate.is_approved(request.action_id):
                self._pending_approvals[request.action_id] = request
                return DispatchResult(
                    action_id=request.action_id, success=False,
                    safety_verdict=verdict, safety_result=safety_result,
                    blueprint_errors=blueprint_errors,
                    total_duration_ms=(time.monotonic() - start) * 1000,
                    pipeline_stages=stages,
                )

        return None  # Not blocked

    # ── Audit Helper ──────────────────────────────────────

    def _log_audit(
        self,
        request: DispatchRequest,
        executor_result: ActionResult,
        safety_result: Optional[SafetyCheckResult],
        stages: Dict[str, float],
    ) -> None:
        """Log the action execution to the audit logger."""
        if request.skip_audit and safety_result and safety_result.verdict == SafetyVerdict.ALLOW:
            return
        audit_start = time.monotonic()
        verdict_str = safety_result.verdict.value if safety_result else "ALLOW"
        category_str = safety_result.category.value if safety_result else "safe"
        self._audit_logger.log_action(
            action_type=request.action_type,
            operation=request.config.get("operation", ""),
            executor_class=(lambda e: type(e).__name__ if e else "Unknown")(self._registry.get_executor(request.action_type)),
            verdict=verdict_str,
            success=executor_result.success,
            duration_ms=executor_result.duration_ms,
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            session_id=request.session_id,
            request_id=request.request_id,
            risk_score=safety_result.risk_score if safety_result else 0.0,
            category=category_str,
            error=executor_result.error,
            metadata={"action_id": request.action_id},
        )
        stages["audit_logging"] = (time.monotonic() - audit_start) * 1000

    # ── Pending Actions ───────────────────────────────────

    def confirm_action(self, action_id: str) -> Optional[DispatchResult]:
        """Confirm a pending action."""
        request = self._pending_confirmations.pop(action_id, None)
        if not request:
            return None
        self._safety_gate.confirm_action(action_id)
        return None

    def approve_action(self, action_id: str, approver_role: str) -> Optional[DispatchResult]:
        """Approve a pending action."""
        request = self._pending_approvals.pop(action_id, None)
        if not request:
            return None
        self._safety_gate.approve_action(action_id, approver_role)
        return None

    def get_pending_confirmations(self) -> Dict[str, Dict[str, Any]]:
        """Get all actions pending user confirmation."""
        return {
            aid: {"action_type": req.action_type, "config": req.config,
                  "reason": "Requires user confirmation"}
            for aid, req in self._pending_confirmations.items()
        }

    def get_pending_approvals(self) -> Dict[str, Dict[str, Any]]:
        """Get all actions pending role approval."""
        return {
            aid: {"action_type": req.action_type, "config": req.config,
                  "reason": "Requires role approval"}
            for aid, req in self._pending_approvals.items()
        }

    @property
    def stats(self) -> Dict[str, Any]:
        """Get dispatcher statistics."""
        return {
            **self._stats,
            "pending_confirmations": len(self._pending_confirmations),
            "pending_approvals": len(self._pending_approvals),
        }

    @property
    def impact_preview(self) -> ImpactPreviewEngine:
        """Lazy-load ImpactPreviewEngine."""
        if self._impact_preview is None:
            self._impact_preview = get_impact_preview_engine()
        return self._impact_preview

    @property
    def policy_engine(self) -> PolicyEngine:
        """Lazy-load PolicyEngine."""
        if self._policy_engine is None:
            self._policy_engine = get_policy_engine()
        return self._policy_engine

    @property
    def db_journal(self) -> DBTransactionJournal:
        """Lazy-load DBTransactionJournal."""
        if self._db_journal is None:
            self._db_journal = get_db_journal()
        return self._db_journal

    @property
    def coordinated_rollback(self) -> CoordinatedRollbackManager:
        """Lazy-load CoordinatedRollbackManager."""
        if self._coordinated_rollback is None:
            self._coordinated_rollback = get_coordinated_rollback_manager()
        return self._coordinated_rollback

    async def preview(self, request: DispatchRequest) -> dict[str, Any]:
        """Preview what would happen if this action were executed (dry-run)."""
        return self.impact_preview.preview_action(
            action_type=request.action_type,
            config=request.config,
            context=request.context,
        ).to_dict()

    def evaluate_policies(self, request: DispatchRequest) -> PolicyDecision:
        """Evaluate policy rules for this action."""
        return self.policy_engine.evaluate(
            action_type=request.action_type,
            config=request.config,
            context=request.context,
        )

    def _validate_blueprint(self, request: DispatchRequest) -> List[str]:
        """Validate the action against the active Blueprint schema."""
        schema = self._blueprint.executor_schemas.get(request.action_type)
        if not schema:
            return []
        return BlueprintValidator.validate_config(request.config, schema)

    # ── Dry-run Integration (Phase C1) ────────────────────

    async def _dry_run_execute(self, request: DispatchRequest) -> ActionResult:
        """Execute action in dry-run mode — simulate without real effects."""
        mock = ActionResult(
            success=True,
            data={"dry_run": True, "simulated": True, "action_type": request.action_type},
            error="", duration_ms=0.0,
        )
        try:
            from ..dry_run_executor import get_dry_run_executor
            dry_runner = get_dry_run_executor()
            ctx = {**request.context, "action_type": request.action_type, "dry_run": True}
            result = await dry_runner.execute(request.config, ctx)
            from ..base import ActionResult as AR
            return result if isinstance(result, AR) else mock
        except ImportError:
            logger.warning("ActionDispatcher: DryRunExecutor not available, returning mock result")
            return mock
        except Exception as exc:
            logger.warning("ActionDispatcher: Dry-run execution failed: %s", exc)
            mock.data["error"] = str(exc)
            return mock
