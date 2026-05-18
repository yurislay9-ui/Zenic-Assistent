"""chain — Type definitions."""

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

