"""
Zenic-Agents Asistente - Approval Chain System (Phase 6.1b)

Chain-of-approval system for critical actions. When SafetyGate returns
APPROVE, the action enters the approval chain. Approvers with sufficient
role must explicitly approve before execution proceeds.

Flow:
  Action → SafetyGate(APPROVE) → ApprovalChain.create_request()
  → Approvers notified → approve()/reject() → Action dispatched

Persistence: SQLite via chain_parts/persistence.py.
Timeout: Auto-escalation to higher authority after configurable delay.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class ApprovalPriority(str, Enum):
    """Priority level for approval requests."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalRequest:
    """A request for approval of a pending action."""
    request_id: str = ""
    action_type: str = ""
    action_config: Dict[str, Any] = field(default_factory=dict)
    required_role: str = "gerente"
    requested_by: int = 0
    status: ApprovalStatus = ApprovalStatus.PENDING
    priority: ApprovalPriority = ApprovalPriority.NORMAL
    created_at: str = ""
    expires_at: str = ""
    approved_by: Optional[int] = None
    approved_at: Optional[str] = None
    rejection_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = f"apr-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def is_expired(self) -> bool:
        """Check if the request has expired."""
        if not self.expires_at:
            return False
        exp = datetime.fromisoformat(self.expires_at)
        return datetime.now(timezone.utc) > exp

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "request_id": self.request_id,
            "action_type": self.action_type,
            "action_config": self.action_config,
            "required_role": self.required_role,
            "requested_by": self.requested_by,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "rejection_reason": self.rejection_reason,
            "metadata": self.metadata,
        }


@dataclass
class ApprovalResult:
    """Result of an approval action."""
    success: bool
    request_id: str
    status: ApprovalStatus
    message: str


# ═══════════════════════════════════════════════════════════════
# GRIETA 3: MemoryApprovalPayload — HITL Mandatory Fields
# ═══════════════════════════════════════════════════════════════

@dataclass
class MemoryApprovalPayload:
    """Payload estricto para aprobación de aprendizajes del Chip.

    GRIETA 3 CERRADA: No podemos depender de que un administrador
    escriba "ok" para modificar la memoria del sistema.

    El objeto de aprobación FALLA la compilación de la regla YAML
    si no cumple esta estructura.

    Mandatory fields:
      1. admin_evidence_review (bool) — MUST be True
      2. admin_justification (str) — MUST be >= 50 characters
      3. risk_acknowledgment (bool) — MUST be True + admin_session_id

    Flow after validation:
      → YAML rendered for hot-reload
      → MerkleLedger sealed with BLAKE3
      → Cache LRU updated
      → Next time: Layer 1 resolves in <5ms, IA not activated
    """

    # ── MANDATORY fields — must pass validate() ──
    admin_evidence_review: bool = False
    admin_justification: str = ""
    risk_acknowledgment: bool = False
    admin_session_id: str = ""

    # ── Auto-populated fields (no admin input required) ──
    mapping_id: str = ""
    ia_question: str = ""
    ia_response: bool = False
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    consensus_score: float = 0.0

    # Minimum character count for admin justification
    MIN_JUSTIFICATION_LEN: int = 50

    def validate(self) -> None:
        """Valida que todos los campos obligatorios estén completos.

        Lanza ValueError si no cumple la estructura.
        El YAML renderer también verifica esto antes de compilar.
        """
        if not self.admin_evidence_review:
            raise ValueError(
                "HITL: admin_evidence_review es OBLIGATORIO. "
                "El administrador debe confirmar que revisó la evidencia "
                "de ejecución generada por las Capas 2 y 3."
            )
        if len(self.admin_justification.strip()) < self.MIN_JUSTIFICATION_LEN:
            raise ValueError(
                f"HITL: admin_justification requiere MÍNIMO "
                f"{self.MIN_JUSTIFICATION_LEN} caracteres. "
                f"Recibidos: {len(self.admin_justification.strip())}. "
                f"Explique por qué esta regla semántica o adaptación "
                f"del DAG es válida para el negocio."
            )
        if not self.risk_acknowledgment:
            raise ValueError(
                "HITL: risk_acknowledgment es OBLIGATORIO. "
                "El administrador debe asumir la responsabilidad "
                "explícita de inyectar esta nueva regla operativa "
                "en el entorno de producción."
            )
        if not self.admin_session_id.strip():
            raise ValueError(
                "HITL: admin_session_id es OBLIGATORIO. "
                "Debe estar ligado al ID criptográfico de la sesión."
            )

    def is_valid(self) -> bool:
        """Returns True if all mandatory fields are valid."""
        try:
            self.validate()
            return True
        except ValueError:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "admin_evidence_review": self.admin_evidence_review,
            "admin_justification": self.admin_justification,
            "risk_acknowledgment": self.risk_acknowledgment,
            "admin_session_id": self.admin_session_id,
            "mapping_id": self.mapping_id,
            "ia_question": self.ia_question,
            "ia_response": self.ia_response,
            "evidence_for": self.evidence_for,
            "evidence_against": self.evidence_against,
            "consensus_score": self.consensus_score,
        }


class ApprovalChain:
    """Chain-of-approval system for critical actions.

    When SafetyGate returns APPROVE, the action enters this chain.
    Approvers with sufficient role must explicitly approve before
    the action can proceed to execution.
    """

    def __init__(
        self,
        db_path: str = "approval_chain.sqlite",
        default_timeout_hours: int = 24,
        escalation_timeout_hours: int = 4,
    ) -> None:
        self._db_path = db_path
        self._default_timeout_hours = default_timeout_hours
        self._escalation_timeout_hours = escalation_timeout_hours
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[ApprovalRequest], None]] = []

        # Use the extracted persistence module
        from .chain_parts.persistence import ApprovalChainDB
        self._db = ApprovalChainDB(db_path)

    # ── Core Operations ────────────────────────────────────

    def create_request(
        self,
        action_type: str,
        action_config: Dict[str, Any],
        requested_by: int,
        required_role: str = "gerente",
        priority: ApprovalPriority = ApprovalPriority.NORMAL,
        timeout_hours: Optional[int] = None,
        tenant_id: str = "__anonymous__",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Create a new approval request for a pending action."""
        timeout = timeout_hours or self._default_timeout_hours
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=timeout) if timeout > 0 else now

        # Phase C3: Risk-based role routing
        if required_role == "gerente":
            risk_role = self.check_risk_routing(
                action_type, action_config, metadata or {},
            )
            if risk_role:
                required_role = risk_role

        request = ApprovalRequest(
            action_type=action_type,
            action_config=action_config,
            required_role=required_role,
            requested_by=requested_by,
            status=ApprovalStatus.PENDING,
            priority=priority,
            expires_at=expires.isoformat() if timeout > 0 else "",
            metadata=metadata or {},
        )

        with self._lock:
            self._db.persist_request(request, tenant_id)

        self._notify_callbacks(request)
        logger.info(
            "ApprovalChain: Request %s created for action '%s' (role=%s)",
            request.request_id, action_type, required_role,
        )
        return request

    def approve(
        self, request_id: str, approver_id: int, approver_role: str,
    ) -> ApprovalResult:
        """Approve a pending request."""
        request = self._db.get_request(request_id)
        if not request:
            return ApprovalResult(False, request_id, ApprovalStatus.PENDING, "Request not found")

        if request.status != ApprovalStatus.PENDING:
            return ApprovalResult(False, request_id, request.status,
                                  f"Request is already {request.status.value}")

        # auth_parts removed — use fallback ROLE_HIERARCHY from auth_service stub
        from src.core.auth_service import ROLE_HIERARCHY
        if ROLE_HIERARCHY.get(approver_role, -1) < ROLE_HIERARCHY.get(request.required_role, -1):
            return ApprovalResult(False, request_id, request.status,
                                  f"Approver role '{approver_role}' insufficient")

        if approver_id == request.requested_by:
            return ApprovalResult(False, request_id, request.status,
                                  "Cannot approve your own request")

        now = datetime.now(timezone.utc).isoformat()
        request.status = ApprovalStatus.APPROVED
        request.approved_by = approver_id
        request.approved_at = now

        with self._lock:
            self._db.update_request(request)

        self._notify_callbacks(request)
        logger.info("ApprovalChain: Request %s approved by user %d", request_id, approver_id)
        return ApprovalResult(True, request_id, ApprovalStatus.APPROVED, "Request approved")

    def reject(
        self, request_id: str, approver_id: int, reason: str = "",
    ) -> ApprovalResult:
        """Reject a pending request."""
        request = self._db.get_request(request_id)
        if not request:
            return ApprovalResult(False, request_id, ApprovalStatus.PENDING, "Request not found")

        if request.status != ApprovalStatus.PENDING:
            return ApprovalResult(False, request_id, request.status,
                                  f"Request is already {request.status.value}")

        request.status = ApprovalStatus.REJECTED
        request.approved_by = approver_id
        request.rejection_reason = reason

        with self._lock:
            self._db.update_request(request)

        self._notify_callbacks(request)
        return ApprovalResult(True, request_id, ApprovalStatus.REJECTED, "Request rejected")

    def cancel(self, request_id: str, cancelled_by: int) -> ApprovalResult:
        """Cancel a pending request (by the requester)."""
        request = self._db.get_request(request_id)
        if not request:
            return ApprovalResult(False, request_id, ApprovalStatus.PENDING, "Request not found")
        if request.requested_by != cancelled_by:
            return ApprovalResult(False, request_id, request.status, "Only requester can cancel")
        if request.status != ApprovalStatus.PENDING:
            return ApprovalResult(False, request_id, request.status, "Request is not pending")

        request.status = ApprovalStatus.CANCELLED
        with self._lock:
            self._db.update_request(request)
        self._notify_callbacks(request)
        return ApprovalResult(True, request_id, ApprovalStatus.CANCELLED, "Request cancelled")

    # ── Query methods ──────────────────────────────────────

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a single approval request by ID."""
        return self._db.get_request(request_id)

    def list_pending(
        self, required_role: Optional[str] = None, tenant_id: Optional[str] = None,
    ) -> List[ApprovalRequest]:
        """List all pending approval requests."""
        return self._db.query_requests(
            status=ApprovalStatus.PENDING, required_role=required_role, tenant_id=tenant_id,
        )

    def list_by_requester(self, requested_by: int) -> List[ApprovalRequest]:
        """List all requests by a specific user."""
        return self._db.query_requests(requested_by=requested_by)

    def list_expired(self) -> List[ApprovalRequest]:
        """Find all pending requests that have expired."""
        pending = self.list_pending()
        return [r for r in pending if r.is_expired()]

    def get_stats(self) -> Dict[str, Any]:
        """Get approval chain statistics."""
        return self._db.get_stats()

    # ── Escalation ─────────────────────────────────────────

    def check_escalations(self) -> List[ApprovalRequest]:
        """Check for expired requests and escalate them."""
        expired = self.list_expired()
        escalated: List[ApprovalRequest] = []

        role_escalation = {"viewer": "operador", "operador": "gerente", "gerente": "admin"}

        for request in expired:
            new_role = role_escalation.get(request.required_role, "admin")
            if new_role == request.required_role:
                request.status = ApprovalStatus.EXPIRED
            else:
                request.required_role = new_role
                request.status = ApprovalStatus.ESCALATED
                now = datetime.now(timezone.utc)
                esc_hours = self._escalation_timeout_hours
                request.expires_at = (now + timedelta(hours=esc_hours)).isoformat() if esc_hours > 0 else ""

            with self._lock:
                self._db.update_request(request)

            self._notify_callbacks(request)
            escalated.append(request)
            logger.info("ApprovalChain: Request %s escalated to '%s'", request.request_id, request.required_role)

        return escalated

    # ── Smart Approval Hooks (Phase C3) ───────────────────

    def check_adaptive_auto_approve(
        self,
        user_id: int,
        action_type: str,
        action_config: Dict[str, Any],
        priority: ApprovalPriority = ApprovalPriority.NORMAL,
    ) -> Optional[ApprovalResult]:
        """Check if this request can be auto-approved based on adaptive history.
        
        Phase C3: Integration with AdaptiveApprovalEngine.
        Never auto-approve CRITICAL or financial actions.
        """
        if priority == ApprovalPriority.CRITICAL:
            return None
        if any(kw in action_type.lower() for kw in ("payment", "financial", "transfer")):
            return None
        
        try:
            from .adaptive import get_adaptive_approval
            adaptive = get_adaptive_approval()
            should_approve, reason = adaptive.check_auto_approve(
                user_id, action_type, action_config,
            )
            if should_approve:
                # Create and immediately approve the request
                request = self.create_request(
                    action_type=action_type,
                    action_config=action_config,
                    requested_by=user_id,
                    priority=priority,
                    metadata={"auto_approved": True, "adaptive_reason": reason},
                )
                return self.approve(request.request_id, user_id, "adaptive_auto")
        except Exception as exc:
            logger.debug("ApprovalChain: adaptive check failed: %s", exc)
        
        return None

    def check_risk_routing(
        self,
        action_type: str,
        action_config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Determine required role based on risk assessment.
        
        Phase C3: Integration with RiskBasedApprovalRouter.
        Returns recommended role or None for default behavior.
        """
        try:
            from .risk_routing import get_risk_router
            router = get_risk_router()
            assessment = router.assess_risk(action_type, action_config, context or {})
            return assessment.recommended_role
        except Exception as exc:
            logger.debug("ApprovalChain: risk routing failed: %s", exc)
        
        return None

    # ── Callbacks ──────────────────────────────────────────

    def on_change(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """Register a callback for approval status changes."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, request: ApprovalRequest) -> None:
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(request)
            except Exception as exc:
                logger.warning("ApprovalChain: callback error: %s", exc)


# ── Singleton ─────────────────────────────────────────────

_approval_chain_instance: Optional[ApprovalChain] = None
_approval_chain_lock = threading.Lock()


def get_approval_chain(db_path: str = "approval_chain.sqlite") -> ApprovalChain:
    """Get or create the global ApprovalChain instance."""
    global _approval_chain_instance
    with _approval_chain_lock:
        if _approval_chain_instance is None:
            _approval_chain_instance = ApprovalChain(db_path=db_path)
        return _approval_chain_instance


def reset_approval_chain() -> None:
    """Reset the global ApprovalChain (for testing)."""
    global _approval_chain_instance
    _approval_chain_instance = None
