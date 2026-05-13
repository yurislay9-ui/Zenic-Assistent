"""
Zenic-Agents Asistente - Defense in Depth Layer 2: Binary Hardening (Phase 6.2)

Layer 2: Nuitka compilation checks + Rust binary integrity.
Verifies that the runtime environment matches expected hardened state.

Checks:
- Running from compiled binary (Nuitka) vs interpreted Python
- Rust FFI library availability and integrity
- Binary signature verification
- Environment hardening flags
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HardeningLevel(str, Enum):
    """Level of binary hardening achieved."""
    NONE = "none"           # Pure Python, no compilation
    PARTIAL = "partial"     # Some components compiled (Rust FFI)
    FULL = "full"           # Nuitka-compiled binary + Rust FFI
    MAXIMUM = "maximum"     # Full + stripped + UPX + code signing


@dataclass
class HardeningStatus:
    """Current hardening status."""
    level: HardeningLevel
    nuitka_compiled: bool
    rust_ffi_available: bool
    binary_signed: bool
    environment_hardened: bool
    details: Dict[str, Any]


class BinaryHardeningLayer:
    """Defense in Depth Layer 2: Binary hardening verification.

    Checks that the runtime environment matches the expected
    hardened configuration. In production, Zenic-Agents should be
    running as a Nuitka-compiled binary with Rust FFI extensions.

    This layer does NOT enforce hardening — it only detects and
    reports the current state. Enforcement is handled by the
    LicenseManager and DegradedMode systems.
    """

    def __init__(self) -> None:
        self._rust_lib: Optional[Any] = None
        self._rust_checked = False

    def check_nuitka_compiled(self) -> bool:
        """Check if running as a Nuitka-compiled binary.

        Nuitka sets __nuitka_version__ and modifies sys.frozen.
        """
        if hasattr(sys, "frozen") and sys.frozen:
            return True
        if "__nuitka_version__" in sys.modules:
            return True
        # Check for Nuitka-specific attributes
        try:
            import __main__
            if hasattr(__main__, "__compiled__"):
                return True
        except (ImportError, AttributeError):
            pass
        return False

    def check_rust_ffi(self) -> bool:
        """Check if the Rust FFI library is available.

        Attempts to load the zenic_core Rust library via ctypes.
        If available, the system can use Rust-accelerated paths.
        """
        if self._rust_checked:
            return self._rust_lib is not None

        self._rust_checked = True

        # Check feature flag first
        if not os.environ.get("ZENIC_USE_RUST_DAG", "0") == "1":
            return False

        # Try loading the shared library
        lib_names = [
            "libzenic_core.so",
            "libzenic_core.dylib",
            "zenic_core.dll",
            "zenic_core.cpython-311-x86_64-linux-gnu.so",
        ]

        for lib_name in lib_names:
            try:
                self._rust_lib = ctypes.CDLL(lib_name)
                logger.info("BinaryHardening: Rust FFI loaded: %s", lib_name)
                return True
            except OSError:
                continue

        # Try from RUST_LIB_PATH
        rust_path = os.environ.get("RUST_LIB_PATH", "")
        if rust_path and os.path.exists(rust_path):
            try:
                self._rust_lib = ctypes.CDLL(rust_path)
                logger.info("BinaryHardening: Rust FFI loaded from env: %s", rust_path)
                return True
            except OSError:
                pass

        logger.debug("BinaryHardening: Rust FFI not available")
        return False

    def check_binary_signature(self) -> bool:
        """Check if the binary has a valid code signature.

        On Linux, checks for .sig file alongside the binary.
        On macOS, uses codesign utility.
        """
        # In Python-interpreted mode, no binary signature exists
        if not self.check_nuitka_compiled():
            return False

        # Check for signature file
        exe_path = sys.executable
        sig_path = exe_path + ".sig"
        if os.path.exists(sig_path):
            return True

        # On macOS, try codesign
        if sys.platform == "darwin":
            try:
                import subprocess
                result = subprocess.run(
                    ["codesign", "-v", exe_path],
                    capture_output=True, timeout=5,
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        return False

    def check_environment_hardening(self) -> bool:
        """Check if environment security flags are set.

        Checks for:
        - ZENIC_ENV=production
        - ZENIC_HARDENED=1
        - No DEBUG mode
        - Secure secrets configured
        """
        checks = {
            "production_env": os.environ.get("ZENIC_ENV") == "production",
            "hardened_flag": os.environ.get("ZENIC_HARDENED") == "1",
            "no_debug": os.environ.get("DEBUG", "").lower() not in ("1", "true", "yes"),
            "secure_secret": os.environ.get("ZENIC_AUTH_SECRET", "changeme") not in {
                "changeme", "secret", "jwt_secret",
                "CHANGE_ME_GENERATE_A_SECURE_JWT_SECRET",
            },
        }
        # All checks must pass for environment to be considered hardened
        return all(checks.values())

    def get_status(self) -> HardeningStatus:
        """Get comprehensive hardening status."""
        nuitka = self.check_nuitka_compiled()
        rust = self.check_rust_ffi()
        signed = self.check_binary_signature()
        env_hard = self.check_environment_hardening()

        # Determine overall level
        if nuitka and rust and signed and env_hard:
            level = HardeningLevel.MAXIMUM
        elif nuitka and rust:
            level = HardeningLevel.FULL
        elif rust or nuitka:
            level = HardeningLevel.PARTIAL
        else:
            level = HardeningLevel.NONE

        return HardeningStatus(
            level=level,
            nuitka_compiled=nuitka,
            rust_ffi_available=rust,
            binary_signed=signed,
            environment_hardened=env_hard,
            details={
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
                "platform": sys.platform,
                "executable": sys.executable,
                "frozen": getattr(sys, "frozen", False),
                "rust_lib_loaded": self._rust_lib is not None,
                "env_checks": {
                    "production": os.environ.get("ZENIC_ENV", "development"),
                    "hardened": os.environ.get("ZENIC_HARDENED", "0"),
                    "debug": os.environ.get("DEBUG", "0"),
                },
            },
        )

    def get_rust_lib(self) -> Optional[Any]:
        """Get the loaded Rust FFI library, if available."""
        return self._rust_lib


# ── Singleton ─────────────────────────────────────────────

_binary_hardening: Optional[BinaryHardeningLayer] = None
_lock = threading.Lock()


def get_binary_hardening() -> BinaryHardeningLayer:
    """Get or create the global BinaryHardeningLayer instance."""
    global _binary_hardening
    with _lock:
        if _binary_hardening is None:
            _binary_hardening = BinaryHardeningLayer()
        return _binary_hardening


def reset_binary_hardening() -> None:
    """Reset the global BinaryHardeningLayer (for testing)."""
    global _binary_hardening
    _binary_hardening = None
