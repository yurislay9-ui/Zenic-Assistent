"""
Zenic-Agents Asistente - Hardware Binding (Phase 6.3)

Hardware fingerprint generation and matching for license binding.
Extracted from license/manager.py for the 400-line limit.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import List

from ..types import HardwareBindingStrength

logger = logging.getLogger(__name__)


def get_hardware_fingerprint() -> str:
    """Generate a hardware fingerprint from system identifiers.

    Combines:
    - /etc/machine-id (Linux)
    - CPU model name
    - Total memory
    - Disk serial (when available)

    Returns:
        SHA-256 hex digest (first 32 chars) of the combined identifiers.
    """
    components: List[str] = []

    # Machine ID (Linux)
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            with open(path, "r") as f:
                components.append(f.read().strip()[:32])
                break
        except (FileNotFoundError, PermissionError):
            continue

    # CPU info
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("model name"):
                    components.append(line.split(":")[1].strip()[:32])
                    break
    except (FileNotFoundError, PermissionError):
        pass

    # Memory
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    components.append(line.split(":")[1].strip()[:16])
                    break
    except (FileNotFoundError, PermissionError):
        pass

    # Disk serial (best-effort)
    try:
        import subprocess
        result = subprocess.run(
            ["lsblk", "-ndo", "SERIAL"], capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            serials = [s.strip() for s in result.stdout.split("\n") if s.strip()]
            if serials:
                components.append(serials[0][:16])
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    combined = "|".join(components) if components else "default-hw"
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def check_hardware_match(
    expected: str, current: str, strength: HardwareBindingStrength,
) -> bool:
    """Check if current hardware matches the expected fingerprint.

    Binding strengths:
    - NONE: Always returns True (no binding)
    - SOFT: First 16 characters must match (allows minor HW changes)
    - STRICT: Exact match required
    """
    if strength == HardwareBindingStrength.NONE:
        return True
    if strength == HardwareBindingStrength.STRICT:
        return expected == current
    # SOFT: first 16 chars must match
    return expected[:16] == current[:16]


def get_encryption_hardware_salt(base_salt: bytes) -> bytes:
    """Create a hardware-bound salt by combining base salt with hardware fingerprint.

    Used by the encryption layer to derive hardware-bound encryption keys,
    ensuring that encrypted data cannot be decrypted on a different machine.
    """
    try:
        fingerprint = get_hardware_fingerprint()
        combined = base_salt + fingerprint.encode()
        return hashlib.sha256(combined).digest()
    except Exception:
        return base_salt
