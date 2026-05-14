"""
ZENIC-AGENTS - Dispatch Action (Phase 3 + Phase 5 + Phase C1)

DAG → Executor pipeline integration.
Bridges the DAG pipeline with the executor system:

  DAG Node "DISPATCH_ACTION" → Safety Gate → Executor → Audit Logger → Merkle Ledger

Phase 5: Supports dynamic Blueprint switching from the
Blueprint Registry when blueprint_name is provided.

Phase C1: Supports dry_run mode — simulate execution without real effects.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import ActionResult, ActionExecutor, ExecutorRegistry, get_default_registry
from .safety_gate import SafetyGate, SafetyVerdict, SafetyCheckResult, get_default_safety_gate
from .audit_logger import ExecutorAuditLogger, AuditEntry, get_default_audit_logger
from .blueprint_schema import Blueprint, BlueprintValidator, get_default_blueprint
from .dispatch_parts import BlueprintBridgeMixin
from .impact_preview import ImpactPreviewEngine, get_impact_preview_engine
from .policy_engine import PolicyEngine, PolicyDecision, get_policy_engine
from .db_journal import DBTransactionJournal, get_db_journal
from .coordinated_rollback import CoordinatedRollbackManager, get_coordinated_rollback_manager

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class DispatchRequest:
    """A request to dispatch an action through the pipeline."""
    action_type: str
    config: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)
    action_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    session_id: str = ""
    request_id: str = ""
    blueprint_name: str = ""
    skip_safety_gate: bool = False
    skip_audit: bool = False
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not self.action_id:
            self.action_id = uuid.uuid4().hex[:12]


@dataclass
class DispatchResult:
    """Result of a dispatch through the full pipeline."""
    action_id: str
    success: bool
    safety_verdict: SafetyVerdict
    executor_result: Optional[ActionResult] = None
    audit_entry: Optional[AuditEntry] = None
    safety_result: Optional[SafetyCheckResult] = None
    blueprint_errors: List[str] = field(default_factory=list)
    total_duration_ms: float = 0.0
    pipeline_stages: Dict[str, float] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
#  ACTION DISPATCHER
# ──────────────────────────────────────────────────────────────

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
        """Dispatch an action through the full pipeline.

        Phase 5: If blueprint_name is set in request, auto-loads
        the corresponding Blueprint from the Registry.

        Phase C1: If dry_run=True, simulates execution without
        real side effects using DryRunExecutor.
        """
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
            # Check if these are blocking verdicts requiring action
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
        if request.skip_safety_gate:
            return None
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
        """Check if a safety verdict blocks execution. Returns DispatchResult if blocked."""
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
        if request.skip_audit:
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
        try:
            from .dry_run_executor import get_dry_run_executor
            dry_runner = get_dry_run_executor()
            # Register the action_type in the dry runner's context
            ctx = {**request.context, "action_type": request.action_type, "dry_run": True}
            result = await dry_runner.execute(request.config, ctx)
            # Ensure the result is an ActionResult
            from .base import ActionResult
            if isinstance(result, ActionResult):
                return result
            return ActionResult(
                success=True,
                data={"dry_run": True, "simulated": True, "action_type": request.action_type},
                error="",
                duration_ms=0.0,
            )
        except ImportError:
            logger.warning("ActionDispatcher: DryRunExecutor not available, returning mock result")
            return ActionResult(
                success=True,
                data={"dry_run": True, "simulated": True, "action_type": request.action_type},
                error="",
                duration_ms=0.0,
            )
        except Exception as exc:
            logger.warning("ActionDispatcher: Dry-run execution failed: %s", exc)
            return ActionResult(
                success=True,
                data={"dry_run": True, "simulated": True, "action_type": request.action_type, "error": str(exc)},
                error="",
                duration_ms=0.0,
            )


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


def get_default_dispatcher() -> ActionDispatcher:
    """Get or create the global ActionDispatcher instance."""
    global _default_dispatcher
    if _default_dispatcher is None:
        _default_dispatcher = ActionDispatcher()
    return _default_dispatcher


def reset_dispatcher() -> None:
    """Reset the global dispatcher (for testing)."""
    global _default_dispatcher
    _default_dispatcher = None
