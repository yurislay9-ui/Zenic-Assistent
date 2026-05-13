"""
Gestor de permisos de herramientas.

Verifica y gestiona los permisos de ejecucion
de cada herramienta por sesion y usuario.

Niveles de permiso:
  - ALLOWED: Ejecucion libre sin confirmacion
  - CONFIRM_REQUIRED: Requiere aprobacion del usuario
  - DENIED: No se puede ejecutar
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ...types.tool_use import ToolPermission, ToolSpec

logger = logging.getLogger("zenic_agents.conversational.tools.permissions")


# ─── Override de permiso ─────────────────────────────────────

@dataclass
class PermissionOverride:
    """Override de permiso para una sesion."""
    session_id: str = ""
    tool_name: str = ""
    permission: ToolPermission = ToolPermission.ALLOWED
    granted_at: float = field(default_factory=time.time)
    expires_at: float = 0.0       # 0 = sin expiracion
    reason: str = ""

    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0.0:
            return False
        return time.time() > self.expires_at


# ─── Session permissions ─────────────────────────────────────

@dataclass
class SessionPermissions:
    """Permisos de una sesion."""
    session_id: str = ""
    allowed_categories: list[str] = field(
        default_factory=lambda: ["general", "web", "code"]
    )
    denied_tools: list[str] = field(default_factory=list)
    overrides: dict[str, PermissionOverride] = field(default_factory=dict)
    auto_approve_safe: bool = True       # Auto-aprobar tools seguras
    require_confirmation_dangerous: bool = True

    def can_use(self, tool_name: str, category: str) -> ToolPermission:
        """Verifica si una tool puede usarse en esta sesion."""
        # Override explicito
        override = self.overrides.get(tool_name)
        if override and not override.is_expired:
            return override.permission

        # Tool denegada
        if tool_name in self.denied_tools:
            return ToolPermission.DENIED

        # Categoria no permitida
        if category not in self.allowed_categories:
            return ToolPermission.DENIED

        # Auto-aprobar seguras
        if self.auto_approve_safe and category in ("general", "web"):
            return ToolPermission.ALLOWED

        # Herramientas peligrosas requieren confirmacion
        if self.require_confirmation_dangerous and category == "system":
            return ToolPermission.CONFIRM_REQUIRED

        return ToolPermission.ALLOWED


class PermissionManager:
    """
    Gestor de permisos de herramientas.

    Mantiene los permisos por sesion y permite
    overrides temporales o permanentes.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionPermissions] = {}
        self._lock = threading.Lock()

    # ─── Session management ───────────────────────────────────

    def create_session(
        self,
        session_id: str,
        allowed_categories: list[str] | None = None,
    ) -> SessionPermissions:
        """Crega los permisos para una nueva sesion."""
        with self._lock:
            perms = SessionPermissions(
                session_id=session_id,
                allowed_categories=allowed_categories or ["general", "web", "code"],
            )
            self._sessions[session_id] = perms
            return perms

    def get_session(self, session_id: str) -> SessionPermissions | None:
        """Obtiene los permisos de una sesion."""
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> bool:
        """Remueve los permisos de una sesion."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    # ─── Permission checking ──────────────────────────────────

    def check(
        self,
        session_id: str,
        tool_name: str,
        spec: ToolSpec,
    ) -> ToolPermission:
        """
        Verifica si una tool puede ejecutarse.

        Orden de prioridad:
          1. Override de sesion
          2. Permiso base del spec
          3. Permisos de categoria de sesion
        """
        session_perms = self._sessions.get(session_id)

        if session_perms:
            session_decision = session_perms.can_use(
                tool_name, spec.category
            )
            # Si la sesion dice DENIED, es DENIED
            if session_decision == ToolPermission.DENIED:
                return ToolPermission.DENIED

        # Permiso base del spec
        if spec.permission == ToolPermission.DENIED:
            return ToolPermission.DENIED

        # Si la sesion dice ALLOWED y el spec no es DENIED
        if session_perms and session_perms.can_use(
            tool_name, spec.category
        ) == ToolPermission.ALLOWED:
            # Pero si el spec requiere confirmacion, mantener
            if spec.permission == ToolPermission.CONFIRM_REQUIRED:
                return ToolPermission.CONFIRM_REQUIRED
            return ToolPermission.ALLOWED

        return spec.permission

    # ─── Overrides ────────────────────────────────────────────

    def grant_override(
        self,
        session_id: str,
        tool_name: str,
        permission: ToolPermission = ToolPermission.ALLOWED,
        duration_seconds: float = 0.0,
        reason: str = "",
    ) -> bool:
        """Otorga un override de permiso temporal o permanente."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False

            expires = 0.0
            if duration_seconds > 0:
                expires = time.time() + duration_seconds

            override = PermissionOverride(
                session_id=session_id,
                tool_name=tool_name,
                permission=permission,
                expires_at=expires,
                reason=reason,
            )
            session.overrides[tool_name] = override
            logger.info(
                f"Override concedido: {tool_name} → {permission.value} "
                f"(sesion={session_id[:8]}...)"
            )
            return True

    def revoke_override(self, session_id: str, tool_name: str) -> bool:
        """Revoca un override de permiso."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            return session.overrides.pop(tool_name, None) is not None

    def deny_tool(self, session_id: str, tool_name: str) -> bool:
        """Niega una tool para una sesion."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            if tool_name not in session.denied_tools:
                session.denied_tools.append(tool_name)
            return True

    # ─── Stats ────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del gestor de permisos."""
        return {
            "active_sessions": len(self._sessions),
            "total_overrides": sum(
                len(s.overrides) for s in self._sessions.values()
            ),
        }
