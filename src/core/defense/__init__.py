"""
Zenic-Agents Asistente - Defense Package (Phase 6.2)

Defense in Depth — 6 layers of security protection:

Layer 1: Anti-Tampering (anti-debug, anti-ptrace, code integrity)
Layer 2: Binary Hardening (Nuitka compilation, Rust FFI, code signing)
Layer 3: Encryption (SQLCipher, Fernet, PBKDF2, hardware binding)
Layer 4: Integrity Verification (hash chains, cross-verification)
Layer 5: ECDSA Licensing (see src/core/license/)
Layer 6: Server-side Secrets (remote verification, grace period)

DefenseManager orchestrates all 6 layers and provides a unified status.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .anti_tampering import (
    AntiTamperingLayer,
    TamperEvent,
    TamperSeverity,
    get_anti_tampering,
    reset_anti_tampering,
)
from .binary_hardening import (
    BinaryHardeningLayer,
    HardeningLevel,
    HardeningStatus,
    get_binary_hardening,
    reset_binary_hardening,
)
from .encryption import (
    EncryptionManager,
    EncryptionLevel,
    EncryptionStatus,
    get_encryption_manager,
    reset_encryption_manager,
)
from .integrity import (
    IntegrityVerifier,
    IntegrityCheckResult,
    IntegrityStatus,
    get_integrity_verifier,
    reset_integrity_verifier,
)
from .server_secrets import (
    ServerSecretsLayer,
    SecretType,
    SecretVerification,
    get_server_secrets,
    reset_server_secrets,
)

logger = logging.getLogger(__name__)


@dataclass
class DefenseStatus:
    """Overall defense-in-depth status across all 6 layers."""
    layer1_anti_tampering: Dict[str, Any] = field(default_factory=dict)
    layer2_binary_hardening: Dict[str, Any] = field(default_factory=dict)
    layer3_encryption: Dict[str, Any] = field(default_factory=dict)
    layer4_integrity: Dict[str, Any] = field(default_factory=dict)
    layer5_licensing: Dict[str, Any] = field(default_factory=dict)
    layer6_server_secrets: Dict[str, Any] = field(default_factory=dict)
    overall_score: float = 0.0
    active_layers: int = 0
    recommendations: List[str] = field(default_factory=list)


class DefenseManager:
    """Orchestrator for all 6 Defense in Depth layers.

    Provides:
    - Unified status across all layers
    - Cross-layer event handling (tampering → degraded mode)
    - Security scoring and recommendations
    - One-stop initialization and monitoring
    """

    def __init__(self) -> None:
        self._anti_tampering = get_anti_tampering()
        self._binary_hardening = get_binary_hardening()
        self._encryption_manager: Optional[EncryptionManager] = None
        self._integrity_verifier = get_integrity_verifier()
        self._server_secrets = get_server_secrets()
        self._license_manager: Optional[Any] = None
        self._callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._lock = threading.Lock()

        # Wire anti-tampering events to defense manager
        self._anti_tampering.on_tamper_detected(self._on_tamper_event)
        self._integrity_verifier.on_integrity_violation(self._on_integrity_violation)

    def _lazy_init_encryption(self) -> EncryptionManager:
        """Lazily initialize encryption manager."""
        if self._encryption_manager is None:
            self._encryption_manager = get_encryption_manager()
        return self._encryption_manager

    def initialize_all(self, start_monitoring: bool = True) -> None:
        """Initialize all defense layers.

        Args:
            start_monitoring: Whether to start background monitoring threads.
        """
        logger.info("DefenseManager: Initializing all defense layers...")

        # Layer 3: Encryption
        self._lazy_init_encryption()

        # Layer 5: Licensing
        try:
            from src.core.license.manager import get_license_manager
            self._license_manager = get_license_manager()
        except ImportError:
            logger.debug("DefenseManager: License manager not available yet")

        # Layer 4: Integrity - establish baselines
        self._establish_integrity_baselines()

        if start_monitoring:
            # Layer 1: Anti-tampering monitoring
            self._anti_tampering.start_monitoring()
            # Layer 4: Integrity monitoring
            watch = self._get_integrity_watch_list()
            if watch:
                self._integrity_verifier.start_monitoring(watch)

        logger.info("DefenseManager: All defense layers initialized")

    def get_status(self) -> DefenseStatus:
        """Get comprehensive status across all 6 layers."""
        # Layer 1
        l1 = self._anti_tampering.get_status()
        # Layer 2
        hardening = self._binary_hardening.get_status()
        l2 = {
            "level": hardening.level.value,
            "nuitka_compiled": hardening.nuitka_compiled,
            "rust_ffi_available": hardening.rust_ffi_available,
            "binary_signed": hardening.binary_signed,
            "environment_hardened": hardening.environment_hardened,
        }
        # Layer 3
        enc = self._lazy_init_encryption()
        enc_status = enc.get_status()
        l3 = {
            "level": enc_status.level.value,
            "fernet_available": enc_status.fernet_available,
            "sqlcipher_available": enc_status.sqlcipher_available,
            "hardware_bound": enc_status.hardware_bound,
        }
        # Layer 4
        l4 = self._integrity_verifier.get_status()
        # Layer 5
        l5: Dict[str, Any] = {}
        if self._license_manager:
            try:
                l5 = self._license_manager.get_status()
            except Exception:
                l5 = {"error": "License status unavailable"}
        # Layer 6
        l6 = self._server_secrets.get_status()

        # Calculate score (0-100)
        score = 0.0
        active = 0
        if l1.get("monitoring_active"):
            score += 15
            active += 1
        if hardening.level != HardeningLevel.NONE:
            score += 15
            active += 1
        if enc_status.level != EncryptionLevel.NONE:
            score += 20
            active += 1
        if l4.get("baselines_count", 0) > 0:
            score += 15
            active += 1
        if l5.get("license_valid", False):
            score += 20
            active += 1
        if l6.get("server_url", "") != "not configured":
            score += 15
            active += 1

        # Recommendations
        recs: List[str] = []
        if not l2["nuitka_compiled"]:
            recs.append("Compile with Nuitka for binary hardening")
        if not l2["rust_ffi_available"]:
            recs.append("Enable Rust FFI for performance and security")
        if not l3["sqlcipher_available"]:
            recs.append("Install pysqlcipher3 or sqlcipher3-binary for database encryption")
        if l6.get("server_url") == "not configured":
            recs.append("Configure ZENIC_LICENSE_SERVER for server-side verification")

        return DefenseStatus(
            layer1_anti_tampering=l1,
            layer2_binary_hardening=l2,
            layer3_encryption=l3,
            layer4_integrity=l4,
            layer5_licensing=l5,
            layer6_server_secrets=l6,
            overall_score=score,
            active_layers=active,
            recommendations=recs,
        )

    # ── Event handlers ─────────────────────────────────────

    def _on_tamper_event(self, event: TamperEvent) -> None:
        """Handle anti-tampering detection events."""
        logger.warning(
            "DefenseManager: Tampering detected! severity=%s method=%s: %s",
            event.severity.value, event.detection_method, event.description,
        )
        self._notify_callbacks("tamper_detected", {
            "severity": event.severity.value,
            "method": event.detection_method,
            "description": event.description,
        })

        # If critical, trigger degraded mode
        if event.severity in (TamperSeverity.HIGH, TamperSeverity.CRITICAL):
            try:
                from src.core.degraded_mode.manager import get_degraded_mode_manager
                dm = get_degraded_mode_manager()
                dm.enter_paralysis(level=1 if event.severity == TamperSeverity.HIGH else 2)
            except ImportError:
                logger.warning("DefenseManager: Degraded mode not available for tamper response")

    def _on_integrity_violation(self, result: IntegrityCheckResult) -> None:
        """Handle integrity verification violations."""
        logger.critical(
            "DefenseManager: Integrity violation! component=%s: %s",
            result.component, result.message,
        )
        self._notify_callbacks("integrity_violation", {
            "component": result.component,
            "status": result.status.value,
            "message": result.message,
        })

    def on_security_event(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register a callback for security events across all layers."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, event_type: str, data: Dict[str, Any]) -> None:
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(event_type, data)
            except Exception as exc:
                logger.warning("DefenseManager: Callback error: %s", exc)

    # ── Helpers ────────────────────────────────────────────

    def _establish_integrity_baselines(self) -> None:
        """Establish integrity baselines for critical components."""
        import os
        base = os.environ.get("ZENIC_ROOT", "")
        if not base:
            candidate = os.path.dirname(os.path.abspath(__file__))
            for _ in range(5):
                if os.path.exists(os.path.join(candidate, "src", "core")):
                    base = candidate
                    break
                candidate = os.path.dirname(candidate)

        if base:
            # auth_parts removed — watch safety_gate.py only
            # (auth_parts/_imports.py no longer exists)
            critical = [
                os.path.join(base, "src", "core", "executors", "safety_gate.py"),
            ]
            for fpath in critical:
                if os.path.exists(fpath):
                    self._integrity_verifier.establish_file_baseline(fpath)

    def _get_integrity_watch_list(self) -> List[str]:
        """Get the list of components to watch for integrity monitoring."""
        import os
        base = os.environ.get("ZENIC_ROOT", "")
        # auth_parts removed — no auth_parts file to watch
        watch: List[str] = []
        return watch


# ── Singleton ─────────────────────────────────────────────

_defense_manager: Optional[DefenseManager] = None
_lock = threading.Lock()


def get_defense_manager() -> DefenseManager:
    """Get or create the global DefenseManager instance."""
    global _defense_manager
    with _lock:
        if _defense_manager is None:
            _defense_manager = DefenseManager()
        return _defense_manager


def reset_defense_manager() -> None:
    """Reset the global DefenseManager (for testing)."""
    global _defense_manager
    _defense_manager = None


__all__ = [
    # Layer 1
    "AntiTamperingLayer", "TamperEvent", "TamperSeverity",
    "get_anti_tampering", "reset_anti_tampering",
    # Layer 2
    "BinaryHardeningLayer", "HardeningLevel", "HardeningStatus",
    "get_binary_hardening", "reset_binary_hardening",
    # Layer 3
    "EncryptionManager", "EncryptionLevel", "EncryptionStatus",
    "get_encryption_manager", "reset_encryption_manager",
    # Layer 4
    "IntegrityVerifier", "IntegrityCheckResult", "IntegrityStatus",
    "get_integrity_verifier", "reset_integrity_verifier",
    # Layer 6
    "ServerSecretsLayer", "SecretType", "SecretVerification",
    "get_server_secrets", "reset_server_secrets",
    # Manager
    "DefenseManager", "DefenseStatus",
    "get_defense_manager", "reset_defense_manager",
]
