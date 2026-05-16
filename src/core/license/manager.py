"""
Zenic-Agents Asistente - License Manager (Phase 6.3)

Central license management: creation, verification, hardware binding,
NTP time check, heartbeat, grace period, and remote kill switch.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .types import (
    LicenseInfo, LicenseStatus, LicenseTier,
    LicenseVerificationResult, HardwareBindingStrength, KillSwitchStatus,
)
from .signer import ECDSASigner, get_signer
from .license_parts.hw_binding import get_hardware_fingerprint, check_hardware_match
from .license_parts.persistence import LicenseDB

logger = logging.getLogger(__name__)


class LicenseManager:
    """Cryptographic license management system.

    Features: ECDSA signing, hardware binding, NTP check,
    heartbeat, grace period, kill switch, license creation API.
    """

    def __init__(
        self, db_path: str = "license_store.sqlite", grace_period_hours: int = 72,
        heartbeat_interval_hours: int = 6, ntp_check: bool = True,
    ) -> None:
        self._grace_period_hours = grace_period_hours
        self._heartbeat_interval = heartbeat_interval_hours
        self._ntp_check = ntp_check
        self._signer = get_signer()
        self._current_license: Optional[LicenseInfo] = None
        self._kill_switch = KillSwitchStatus(active=False)
        self._last_heartbeat: float = 0.0
        self._ntp_offset: float = 0.0
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False
        self._db = LicenseDB(db_path)
        self._current_license = self._db.load_cached_license()

    # ── License Creation ───────────────────────────────────

    def create_license(
        self, tier: LicenseTier, issued_to: str, features: Optional[List[str]] = None,
        max_users: int = 1, expires_days: int = 0,
        hardware_binding: HardwareBindingStrength = HardwareBindingStrength.SOFT,
    ) -> LicenseInfo:
        """Create and sign a new license."""
        import secrets
        license_id = f"zl-{secrets.token_hex(8)}"
        now = time.time()
        expires_at = now + (expires_days * 86400) if expires_days > 0 else 0.0
        hw_id = get_hardware_fingerprint() if hardware_binding != HardwareBindingStrength.NONE else ""

        if features is None:
            tier_features = {
                LicenseTier.STARTER: ["basic_pipeline", "chat_completions"],
                LicenseTier.TRIAL: ["basic_pipeline", "chat_completions", "app_generation",
                                     "automation_generation", "schema_design",
                                     "thinking_engine", "reasoning_engine", "logic_chains"],
                LicenseTier.BUSINESS: ["basic_pipeline", "chat_completions", "app_generation",
                                  "automation_generation", "schema_design", "thinking_engine",
                                  "reasoning_engine", "logic_chains"],
                LicenseTier.ENTERPRISE: ["all"],
                LicenseTier.ON_PREMISE_ENTERPRISE: ["all"],
            }
            features = tier_features.get(tier, ["basic_pipeline"])

        info = LicenseInfo(
            license_id=license_id, tier=tier, status=LicenseStatus.ACTIVE,
            issued_to=issued_to, issued_at=now, expires_at=expires_at,
            features=features, max_users=max_users, hardware_id=hw_id,
            binding_strength=hardware_binding,
        )
        info.signature = self._signer.sign(info.to_signable_data())
        self._current_license = info
        self._db.persist_license(info)
        logger.info("LicenseManager: Created license %s (tier=%s)", license_id, tier.value)
        return info

    # ── Verification ───────────────────────────────────────

    def verify(self, license_info: Optional[LicenseInfo] = None) -> LicenseVerificationResult:
        """Verify a license comprehensively."""
        info = license_info or self._current_license
        if not info:
            return LicenseVerificationResult(False, LicenseStatus.INVALID, reason="No license loaded",
                                             checks_performed=["no_license"])

        checks: List[str] = []

        # 1. Signature
        sig_valid = self._signer.verify(info.to_signable_data(), info.signature)
        checks.append(f"signature:{'ok' if sig_valid else 'FAIL'}")
        if not sig_valid:
            info.status = LicenseStatus.INVALID
            return LicenseVerificationResult(False, LicenseStatus.INVALID, info, "Invalid signature", checks)

        # 2. Kill switch
        if self._kill_switch.active:
            checks.append("kill_switch:ACTIVE")
            info.status = LicenseStatus.REVOKED
            return LicenseVerificationResult(False, LicenseStatus.REVOKED, info,
                                             f"Kill switch: {self._kill_switch.reason}", checks)

        # 3. Expiration (with NTP)
        ntp_time = time.time() + self._ntp_offset
        is_expired = info.expires_at > 0 and ntp_time > info.expires_at
        checks.append(f"expiry:{'expired' if is_expired else 'ok'}")
        if is_expired:
            hours_expired = (ntp_time - info.expires_at) / 3600
            if hours_expired <= self._grace_period_hours:
                info.status = LicenseStatus.GRACE_PERIOD
                return LicenseVerificationResult(True, LicenseStatus.GRACE_PERIOD, info,
                                                 "Within grace period", checks)
            info.status = LicenseStatus.EXPIRED
            return LicenseVerificationResult(False, LicenseStatus.EXPIRED, info, "License expired", checks)

        # 4. Hardware binding
        if info.hardware_id and info.binding_strength != HardwareBindingStrength.NONE:
            current_hw = get_hardware_fingerprint()
            hw_match = check_hardware_match(info.hardware_id, current_hw, info.binding_strength)
            checks.append(f"hardware:{'ok' if hw_match else 'MISMATCH'}")
            if not hw_match:
                info.status = LicenseStatus.INVALID
                return LicenseVerificationResult(False, LicenseStatus.INVALID, info,
                                                 "Hardware mismatch", checks)

        info.status = LicenseStatus.ACTIVE
        return LicenseVerificationResult(True, LicenseStatus.ACTIVE, info, "License valid", checks)

    def get_current_license(self) -> Optional[LicenseInfo]:
        return self._current_license

    def is_licensed(self) -> bool:
        return self.verify().valid

    def has_feature(self, feature: str) -> bool:
        if not self._current_license:
            return False
        return self._current_license.has_feature(feature)

    # ── Kill Switch ────────────────────────────────────────

    def activate_kill_switch(self, reason: str = "", source: str = "config") -> None:
        self._kill_switch = KillSwitchStatus(active=True, reason=reason,
                                              activated_at=time.time(), source=source)
        self._db.persist_kill_switch(self._kill_switch.active, reason,
                                      self._kill_switch.activated_at or time.time(), source)
        logger.critical("LicenseManager: KILL SWITCH ACTIVATED - %s", reason)
        self._notify_callbacks("kill_switch_activated", {"reason": reason})

    def deactivate_kill_switch(self, source: str = "config") -> None:
        self._kill_switch = KillSwitchStatus(active=False)
        self._notify_callbacks("kill_switch_deactivated", {})

    def check_remote_kill_switch(self) -> bool:
        server_url = os.environ.get("ZENIC_LICENSE_SERVER", "")
        if not server_url:
            return False
        try:
            import urllib.request
            req = urllib.request.Request(f"{server_url}/api/v1/kill-switch", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("active", False):
                    self.activate_kill_switch(data.get("reason", "Remote kill switch"), "server")
                    return True
        except Exception:
            pass
        return False

    # ── NTP Check ──────────────────────────────────────────

    def check_ntp_time(self) -> float:
        if not self._ntp_check:
            return 0.0
        try:
            import socket, struct
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(5)
            ntp_server = os.environ.get("ZENIC_NTP_SERVER", "pool.ntp.org")
            client.sendto(b"\x1b" + 47 * b"\0", (ntp_server, 123))
            response, _ = client.recvfrom(1024)
            client.close()
            if len(response) >= 48:
                tx_time = struct.unpack("!Q", response[40:48])[0]
                self._ntp_offset = (tx_time / (2**32) - 2208988800) - time.time()
                return self._ntp_offset
        except Exception as exc:
            logger.debug("LicenseManager: NTP check failed: %s", exc)
        return 0.0

    # ── Heartbeat ──────────────────────────────────────────

    def start_heartbeat(self) -> None:
        if self._running:
            return
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="license-heartbeat",
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._running = False

    def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                self._perform_heartbeat()
            except Exception:
                pass
            time.sleep(self._heartbeat_interval * 3600)

    def _perform_heartbeat(self) -> bool:
        server_url = os.environ.get("ZENIC_LICENSE_SERVER", "")
        if not server_url or not self._current_license:
            return False
        try:
            import urllib.request
            payload = json.dumps({
                "license_id": self._current_license.license_id,
                "hardware_id": get_hardware_fingerprint(), "timestamp": time.time(),
            }).encode()
            req = urllib.request.Request(
                f"{server_url}/api/v1/heartbeat", data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode())
                self._last_heartbeat = time.time()
                if body.get("kill_switch", False):
                    self.activate_kill_switch(body.get("reason", "Server kill switch"), "server")
                    return False
                return True
        except Exception:
            return False

    # ── Callbacks ──────────────────────────────────────────

    def on_license_event(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        self._callbacks.append(callback)

    def _notify_callbacks(self, event_type: str, data: Dict[str, Any]) -> None:
        for cb in self._callbacks:
            try:
                cb(event_type, data)
            except Exception:
                pass

    # ── Status ─────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        info = self._current_license
        return {
            "license_valid": info is not None and info.status == LicenseStatus.ACTIVE,
            "license_id": info.license_id if info else "",
            "tier": info.tier.value if info else "none",
            "status": info.status.value if info else "no_license",
            "issued_to": info.issued_to if info else "",
            "expires_at": info.expires_at if info else 0,
            "days_remaining": info.days_remaining() if info else 0,
            "is_perpetual": info.is_perpetual() if info else False,
            "hardware_bound": bool(info.hardware_id) if info else False,
            "kill_switch_active": self._kill_switch.active,
            "last_heartbeat": self._last_heartbeat,
            "ntp_offset_seconds": self._ntp_offset,
            "signer_using_fallback": self._signer.is_using_fallback(),
            "features": info.features if info else [],
        }


# ── Singleton ─────────────────────────────────────────────

_license_manager: Optional[LicenseManager] = None
_lock = threading.Lock()


def get_license_manager(**kwargs: Any) -> LicenseManager:
    global _license_manager
    with _lock:
        if _license_manager is None:
            _license_manager = LicenseManager(**kwargs)
        return _license_manager


def reset_license_manager() -> None:
    global _license_manager
    if _license_manager and _license_manager._running:
        _license_manager.stop_heartbeat()
    _license_manager = None
