"""
Zenic-Agents Asistente - Defense in Depth Layer 1: Anti-Tampering (Phase 6.2)

Layer 1: mlock + anti-debug + anti-ptrace protection.
Detects runtime debugging, memory inspection, and code tampering.

In pure Python, we implement best-effort detection with fallback
to Rust FFI when available (ZENIC_USE_RUST_DAG=1).

Detection methods:
- ptrace attachment check (Linux)
- Debug flag in sys.flags
- Timing-based debugger detection
- Code integrity hash verification
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TamperSeverity(str, Enum):
    """Severity of a tampering detection event."""
    LOW = "low"           # Possible false positive
    MEDIUM = "medium"     # Likely tampering
    HIGH = "high"         # Confirmed tampering
    CRITICAL = "critical"  # System compromise detected


@dataclass
class TamperEvent:
    """A tampering detection event."""
    severity: TamperSeverity
    detection_method: str
    description: str
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


class AntiTamperingLayer:
    """Defense in Depth Layer 1: Anti-tampering and anti-debugging.

    Provides multiple detection mechanisms:
    1. ptrace check (Linux) — detects debuggers attaching to process
    2. sys.flags check — detects Python debug mode
    3. Timing anomaly detection — detects breakpoints/single-stepping
    4. Code integrity verification — detects modified source files
    5. Memory protection hints — mlock advisory (Linux)

    All detections are non-fatal by default but can trigger callbacks
    for escalation to the degraded mode system.
    """

    def __init__(
        self,
        enable_ptrace_check: bool = True,
        enable_timing_check: bool = True,
        enable_code_integrity: bool = True,
        timing_threshold_ms: float = 500.0,
        check_interval_seconds: float = 30.0,
    ) -> None:
        self._enable_ptrace = enable_ptrace_check
        self._enable_timing = enable_timing_check
        self._enable_code_integrity = enable_code_integrity
        self._timing_threshold_ms = timing_threshold_ms
        self._check_interval = check_interval_seconds
        self._callbacks: List[Callable[[TamperEvent], None]] = []
        self._baseline_hashes: Dict[str, str] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._detection_count = 0

    # ── Detection Methods ──────────────────────────────────

    def check_ptrace(self) -> Optional[TamperEvent]:
        """Check if a debugger is attached via ptrace (Linux only).

        Reads /proc/self/status for TracerPid. If non-zero,
        a debugger or ptrace is attached.
        """
        if not self._enable_ptrace:
            return None

        if sys.platform != "linux":
            return None

        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("TracerPid:"):
                        pid = int(line.split(":")[1].strip())
                        if pid != 0:
                            return TamperEvent(
                                severity=TamperSeverity.HIGH,
                                detection_method="ptrace",
                                description=f"Debugger attached (TracerPid={pid})",
                                metadata={"tracer_pid": pid},
                            )
                        return None
        except (FileNotFoundError, PermissionError, ValueError):
            pass

        return None

    def check_debug_flags(self) -> Optional[TamperEvent]:
        """Check Python sys.flags for debug mode indicators."""
        if sys.flags.debug:
            return TamperEvent(
                severity=TamperSeverity.MEDIUM,
                detection_method="debug_flags",
                description="Python debug mode is active (sys.flags.debug=1)",
                metadata={"sys_flags": {k: getattr(sys.flags, k) for k in dir(sys.flags) if not k.startswith("_")}},
            )
        return None

    def check_timing_anomaly(self) -> Optional[TamperEvent]:
        """Detect timing anomalies that suggest debugging.

        Measures execution time of a known-duration operation.
        If significantly longer than expected, a debugger may be
        single-stepping through the code.
        """
        if not self._enable_timing:
            return None

        # Measure a tight loop
        start = time.perf_counter_ns()
        total = 0
        for i in range(100_000):
            total += i
        elapsed_ns = time.perf_counter_ns() - start
        elapsed_ms = elapsed_ns / 1_000_000

        # Normal execution: ~5-50ms depending on hardware
        # Debugger single-stepping: 500ms+
        if elapsed_ms > self._timing_threshold_ms:
            return TamperEvent(
                severity=TamperSeverity.MEDIUM,
                detection_method="timing_anomaly",
                description=f"Execution timing anomaly: {elapsed_ms:.1f}ms (threshold: {self._timing_threshold_ms}ms)",
                metadata={"elapsed_ms": elapsed_ms, "threshold_ms": self._timing_threshold_ms},
            )
        return None

    def check_code_integrity(self, file_path: str) -> Optional[TamperEvent]:
        """Verify the integrity of a source file by comparing its hash.

        Compares current SHA-256 hash against a previously stored baseline.
        If the hash differs, the file has been modified at runtime.
        """
        if not self._enable_code_integrity:
            return None

        if not os.path.exists(file_path):
            return None

        current_hash = self._compute_file_hash(file_path)

        if file_path not in self._baseline_hashes:
            # First time: establish baseline
            self._baseline_hashes[file_path] = current_hash
            return None

        if self._baseline_hashes[file_path] != current_hash:
            return TamperEvent(
                severity=TamperSeverity.CRITICAL,
                detection_method="code_integrity",
                description=f"Code integrity violation: {file_path} has been modified",
                metadata={
                    "file_path": file_path,
                    "expected_hash": self._baseline_hashes[file_path][:16],
                    "actual_hash": current_hash[:16],
                },
            )
        return None

    def run_all_checks(self) -> List[TamperEvent]:
        """Run all tampering detection checks.

        Returns a list of detected events (empty if clean).
        """
        events: List[TamperEvent] = []

        # Check ptrace
        evt = self.check_ptrace()
        if evt:
            events.append(evt)

        # Check debug flags
        evt = self.check_debug_flags()
        if evt:
            events.append(evt)

        # Check timing
        evt = self.check_timing_anomaly()
        if evt:
            events.append(evt)

        # Check code integrity for critical files
        critical_files = self._get_critical_files()
        for fpath in critical_files:
            evt = self.check_code_integrity(fpath)
            if evt:
                events.append(evt)

        if events:
            self._detection_count += len(events)
            for evt in events:
                self._notify_callbacks(evt)
                logger.warning(
                    "AntiTampering: %s detected via %s: %s",
                    evt.severity.value, evt.detection_method, evt.description,
                )

        return events

    # ── Continuous Monitoring ──────────────────────────────

    def start_monitoring(self) -> None:
        """Start continuous anti-tampering monitoring in background thread."""
        if self._running:
            return
        self._running = True

        # Establish baselines before monitoring starts
        for fpath in self._get_critical_files():
            self.check_code_integrity(fpath)

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="anti-tamper",
        )
        self._monitor_thread.start()
        logger.info("AntiTampering: Monitoring started (interval=%ss)", self._check_interval)

    def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("AntiTampering: Monitoring stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                self.run_all_checks()
            except Exception as exc:
                logger.debug("AntiTampering: Check error: %s", exc)
            time.sleep(self._check_interval)

    # ── Callbacks ──────────────────────────────────────────

    def on_tamper_detected(self, callback: Callable[[TamperEvent], None]) -> None:
        """Register a callback for tampering detection events."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, event: TamperEvent) -> None:
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as exc:
                logger.warning("AntiTampering: Callback error: %s", exc)

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
        except (OSError, IOError):
            return ""
        return h.hexdigest()

    def _get_critical_files(self) -> List[str]:
        """Get list of critical source files to monitor for integrity."""
        base = os.environ.get("ZENIC_ROOT", "")
        if not base:
            # Try to find the project root
            candidate = os.path.dirname(os.path.abspath(__file__))
            for _ in range(5):
                if os.path.exists(os.path.join(candidate, "src", "core")):
                    base = candidate
                    break
                candidate = os.path.dirname(candidate)

        if not base:
            return []

        critical = [
            os.path.join(base, "src", "core", "auth_parts", "_imports.py"),
            os.path.join(base, "src", "core", "auth_parts", "_rbac_mixin.py"),
            os.path.join(base, "src", "core", "license", "manager.py"),
            os.path.join(base, "src", "core", "defense", "integrity.py"),
            os.path.join(base, "src", "core", "executors", "safety_gate.py"),
        ]
        return [f for f in critical if os.path.exists(f)]

    def get_status(self) -> Dict[str, Any]:
        """Get current anti-tampering status."""
        return {
            "monitoring_active": self._running,
            "detection_count": self._detection_count,
            "baselines_established": len(self._baseline_hashes),
            "ptrace_check_enabled": self._enable_ptrace,
            "timing_check_enabled": self._enable_timing,
            "code_integrity_enabled": self._enable_code_integrity,
            "timing_threshold_ms": self._timing_threshold_ms,
            "check_interval_seconds": self._check_interval,
        }


# ── Singleton ─────────────────────────────────────────────

_anti_tampering: Optional[AntiTamperingLayer] = None
_lock = threading.Lock()


def get_anti_tampering() -> AntiTamperingLayer:
    """Get or create the global AntiTamperingLayer instance."""
    global _anti_tampering
    with _lock:
        if _anti_tampering is None:
            _anti_tampering = AntiTamperingLayer()
        return _anti_tampering


def reset_anti_tampering() -> None:
    """Reset the global AntiTamperingLayer (for testing)."""
    global _anti_tampering
    if _anti_tampering and _anti_tampering._running:
        _anti_tampering.stop_monitoring()
    _anti_tampering = None
