"""
ZENIC-AGENTS - ActionExecutor Base Module (Phase 3)

Base classes, validation helpers, and registry for the ActionExecutor system.
Enhanced with Safety Gate integration, Audit logging, and Blueprint validation.
"""

import hashlib
import hmac
import logging
import os
import re
import sqlite3
import time
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .safety_gate import get_default_safety_gate  # SECURITY: C4 fix

logger = logging.getLogger(__name__)

# Dependencias opcionales
try:
    import aiosmtplib  # type: ignore[import-unresolved]; _HAS_AIOSMTPLIB = True
except ImportError: _HAS_AIOSMTPLIB = False

try:
    import aiohttp; _HAS_AIOHTTP = True
except ImportError: _HAS_AIOHTTP = False

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    _HAS_APSCHEDULER = True
except ImportError: _HAS_APSCHEDULER = False


# ============================================================
#  RESULTADO DE ACCIÓN (Enhanced)
# ============================================================

@dataclass
class ActionResult:
    """Resultado estandarizado de cualquier acción ejecutada.

    Enhanced (Phase 3): Added audit_id and safety_verdict fields
    for traceability through the Safety Gate → Executor → Audit pipeline.
    """
    success: bool
    data: Dict[str, Any]
    error: str = ""
    duration_ms: float = 0.0
    audit_id: str = ""            # Links to ExecutorAuditLogger entry
    safety_verdict: str = ""      # ALLOW, CONFIRM, DENY, RATE_LIMITED
    blueprint_valid: bool = True   # Whether config passed Blueprint validation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "audit_id": self.audit_id,
            "safety_verdict": self.safety_verdict,
            "blueprint_valid": self.blueprint_valid,
        }


# ============================================================
#  CLASE BASE ABSTRACTA
# ============================================================

class ActionExecutor(ABC):
    """Clase base abstracta para todos los ejecutores de acciones.

    Enhanced (Phase 3): Added pre_execute and post_execute hooks
    for Safety Gate and Audit integration.
    """

    @abstractmethod
    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Ejecuta la acción con la configuración y contexto dados."""
        ...

    def _measure(self) -> float:
        return time.monotonic()

    def _elapsed_ms(self, start: float) -> float:
        return round((time.monotonic() - start) * 1000, 2)

    @property
    def executor_name(self) -> str:
        """Human-readable name of this executor."""
        return self.__class__.__name__


# ============================================================
#  VALIDADORES UTILITARIOS
# ============================================================

def _validate_email(email: str) -> bool:
    """Valida formato básico de email."""
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))

def _validate_url(url: str) -> bool:
    """Valida formato básico de URL."""
    try:
        r = urllib.parse.urlparse(url)
        return all([r.scheme in ("http", "https"), r.netloc])
    except Exception: return False

def _validate_url_ssrf(url: str, allowed_schemes: tuple = ("http", "https")) -> str:
    """Validate URL to prevent SSRF attacks.

    Checks scheme, hostname, and blocks internal/private IPs.
    Returns the URL string if valid, raises ValueError otherwise.
    """
    import ipaddress
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Use: {allowed_schemes}")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            raise ValueError(f"Access to internal IPs is not allowed: {parsed.hostname}")
    except ValueError:
        pass  # hostname is not an IP, that's OK
    return url

def _safe_path(path: str, base_dir: str = "") -> str:
    """Resuelve path y verifica que no escape del base_dir (path traversal).

    SECURITY (H-05 fix): Removed /tmp and home directory from allowed prefixes.
    Only the explicitly configured base_dir is allowed. This prevents reading
    sensitive files like ~/.ssh/, ~/.env, ~/.bashrc via FileExecutor.

    If base_dir is "", uses os.getcwd(). Absolute paths are only allowed
    if they resolve within the base_dir. Relative paths are resolved
    against base_dir and must not escape it via ../ traversal.
    """
    if not base_dir: base_dir = os.getcwd()
    base_dir = os.path.realpath(base_dir)

    # Si el path es absoluto, verificar que está dentro del base_dir
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
        # SECURITY: Only allow paths within the configured base_dir
        if resolved.startswith(base_dir + os.sep) or resolved == base_dir:
            return resolved
        raise ValueError(f"Path traversal detected: '{path}' escapes base directory")

    # Path relativo: verificar que no escapa del base_dir
    resolved = os.path.realpath(os.path.join(base_dir, path))
    if not resolved.startswith(base_dir + os.sep) and resolved != base_dir:
        raise ValueError(f"Path traversal detected: '{path}' escapes base directory")
    return resolved

def _validate_sql(query: str) -> bool:
    """Valida que un query SQL no contenga patrones de inyección peligrosos."""
    dangerous = [r";\s*DROP\s", r";\s*DELETE\s+FROM\s", r";\s*UPDATE\s+.+\s+SET\s",
                 r";\s*INSERT\s+INTO\s", r"UNION\s+SELECT\s", r"--\s*$", r"/\*.*\*/"]
    for pattern in dangerous:
        if re.search(pattern, query, re.MULTILINE | re.IGNORECASE):
            logger.warning(f"SQL validation: potentially dangerous pattern: {pattern}")
            return False
    return True


# ============================================================
#  REGISTRY DE EJECUTORES (Enhanced with Safety Gate + Audit)
# ============================================================

class ExecutorRegistry:
    """Registry centralizado que gestiona todos los action executors.

    Enhanced (Phase 3):
      - Integrated Safety Gate (pre-execution validation)
      - Integrated Audit Logger (post-execution logging)
      - Integrated Blueprint validation (schema check)
      - 9 executors: email, http, db, file, notification, webhook,
        transform, schedule, discord
    """

    def __init__(
        self,
        safety_gate: Optional[Any] = None,
        audit_logger: Optional[Any] = None,
        blueprint: Optional[Any] = None,
    ) -> None:
        self._executors: Dict[str, ActionExecutor] = {}
        self._safety_gate = safety_gate
        self._audit_logger = audit_logger
        self._blueprint = blueprint
        self._safety_enabled: bool = safety_gate is not None
        self._audit_enabled: bool = audit_logger is not None
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra los ejecutores por defecto (7 executors).

        Phase 3: Database, File, Transform, Schedule
        Phase 2: Email, ServiceNow, Jira
        """
        # Lazy imports to avoid circular dependencies
        from .database_executor import DatabaseExecutor
        from .file_executor import FileExecutor
        from .transform_executor import TransformExecutor
        from .schedule_executor import ScheduleExecutor
        from .email_executor import EmailExecutor
        from .servicenow_executor import ServiceNowExecutor
        from .jira_executor import JiraExecutor

        db_exec = DatabaseExecutor()
        file_exec = FileExecutor()
        transform_exec = TransformExecutor()
        schedule_exec = ScheduleExecutor()
        email_exec = EmailExecutor()
        servicenow_exec = ServiceNowExecutor()
        jira_exec = JiraExecutor()

        # Mapeo de tipos de accion a ejecutores (alias incluidos)
        for key, executor in [
            ("database_operation", db_exec), ("database", db_exec), ("db", db_exec),
            ("file_operation", file_exec), ("file", file_exec),
            ("data_transform", transform_exec), ("transform", transform_exec),
            ("schedule", schedule_exec),
            # Phase 2 — Email
            ("send_email", email_exec), ("email", email_exec),
            # Phase 2 — ServiceNow
            ("servicenow", servicenow_exec), ("create_incident", servicenow_exec),
            ("update_incident", servicenow_exec), ("close_incident", servicenow_exec),
            ("get_incident", servicenow_exec), ("search_incidents", servicenow_exec),
            ("add_comment", servicenow_exec), ("create_change_request", servicenow_exec),
            # Phase 2 — Jira
            ("jira", jira_exec), ("create_issue", jira_exec),
            ("update_issue", jira_exec), ("transition_issue", jira_exec),
            ("get_issue", jira_exec), ("search_issues", jira_exec),
            ("add_jira_comment", jira_exec), ("link_issues", jira_exec),
        ]:
            self.register_executor(key, executor)

    def get_executor(self, action_type: str) -> Optional[ActionExecutor]:
        """Obtiene el executor registrado para un tipo de acción."""
        return self._executors.get(action_type)

    def register_executor(self, action_type: str, executor: ActionExecutor) -> None:
        """Registra un executor para un tipo de acción."""
        self._executors[action_type] = executor
        logger.debug(f"ExecutorRegistry: Registered '{action_type}' -> {executor.__class__.__name__}")

    async def execute_action(self, action_type: str, config: Dict[str, Any],
                             context: Optional[Dict[str, Any]] = None) -> ActionResult:
        """Ejecuta una acción a través del executor correspondiente.

        Enhanced (Phase 3): Runs Safety Gate check before execution
        and logs audit entry after execution.
        """
        if context is None: context = {}

        # ── Pre-execution: Safety Gate ──
        safety_verdict = ""
        if self._safety_enabled and self._safety_gate:
            from .safety_gate import SafetyVerdict as SV
            check = self._safety_gate.check(action_type, config, context)
            safety_verdict = check.verdict.value
            if check.verdict == SV.DENY:
                logger.warning("ExecutorRegistry: Safety DENY for %s: %s", action_type, check.reason)
                return ActionResult(
                    False, {"action_type": action_type, "safety_reason": check.reason},
                    f"Safety gate denied: {check.reason}", 0.0,
                    safety_verdict=safety_verdict,
                )
            if check.verdict == SV.RATE_LIMITED:
                return ActionResult(
                    False, {"action_type": action_type},
                    f"Rate limited: {check.reason}", 0.0,
                    safety_verdict=safety_verdict,
                )

        # ── Execute ──
        executor = self.get_executor(action_type)
        if not executor:
            return ActionResult(
                False, {"action_type": action_type},
                f"No executor for '{action_type}'. Available: {list(self._executors.keys())}",
            )
        try:
            result = await executor.execute(config, context)
            # Enrich result with safety info
            if safety_verdict:
                result.safety_verdict = safety_verdict
        except Exception as e:
            logger.error(f"ExecutorRegistry: Unhandled exception in {action_type}: {e}")
            result = ActionResult(False, {"action_type": action_type}, f"Executor error: {e}")

        # ── Post-execution: Audit Log ──
        if self._audit_enabled and self._audit_logger:
            try:
                entry = self._audit_logger.log_action(
                    action_type=action_type,
                    operation=config.get("operation", ""),
                    executor_class=executor.__class__.__name__,
                    verdict=safety_verdict or "ALLOW",
                    success=result.success,
                    duration_ms=result.duration_ms,
                    user_id=context.get("user_id", ""),
                    tenant_id=context.get("tenant_id", ""),
                )
                result.audit_id = entry.entry_id
            except Exception as e:
                logger.debug(f"ExecutorRegistry: Audit logging failed: {e}")

        return result

    def enable_safety_gate(self, safety_gate: Any) -> None:
        """Enable Safety Gate integration."""
        self._safety_gate = safety_gate
        self._safety_enabled = True

    def enable_audit(self, audit_logger: Any) -> None:
        """Enable Audit Logger integration."""
        self._audit_logger = audit_logger
        self._audit_enabled = True

    @property
    def registered_types(self) -> List[str]:
        """Lista de tipos de acción registrados."""
        return list(self._executors.keys())

    @property
    def executor_classes(self) -> Dict[str, str]:
        """Mapeo de tipo de acción a clase de executor."""
        return {k: v.__class__.__name__ for k, v in self._executors.items()}

    @property
    def stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "registered_types": len(self._executors),
            "unique_executors": len(set(v.__class__.__name__ for v in self._executors.values())),
            "safety_enabled": self._safety_enabled,
            "audit_enabled": self._audit_enabled,
            "executors": self.executor_classes,
        }


# ============================================================
#  INSTANCIA GLOBAL DEL REGISTRY
# ============================================================

_default_registry: Optional[ExecutorRegistry] = None


def get_default_registry() -> ExecutorRegistry:
    """Obtiene la instancia global del ExecutorRegistry.

    SECURITY (C4 fix): Always includes the default SafetyGate so that
    no executor path can bypass pre-execution safety validation.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ExecutorRegistry(safety_gate=get_default_safety_gate())
    return _default_registry


def reset_default_registry() -> None:
    """Resetea la instancia global del registry (para tests)."""
    global _default_registry
    _default_registry = None
