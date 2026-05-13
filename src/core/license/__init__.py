"""
Zenic-Agents Asistente - License Package (Phase 6.3)

Cryptographic licensing system with ECDSA signing, hardware binding,
NTP time verification, remote kill switch, and heartbeat.

Components:
- LicenseManager: Central license lifecycle management
- ECDSASigner: ECDSA/HMAC signing and verification
- LicenseInfo, LicenseStatus, LicenseTier: License data types
- KillSwitchStatus: Remote kill switch state
"""

from .types import (
    LicenseTier,
    LicenseStatus,
    HardwareBindingStrength,
    LicenseInfo,
    LicenseVerificationResult,
    KillSwitchStatus,
)
from .signer import (
    ECDSASigner,
    get_signer,
    sign_data,
    verify_signature,
)
from .manager import (
    LicenseManager,
    get_license_manager,
    reset_license_manager,
)

__all__ = [
    # Types
    "LicenseTier",
    "LicenseStatus",
    "HardwareBindingStrength",
    "LicenseInfo",
    "LicenseVerificationResult",
    "KillSwitchStatus",
    # Signer
    "ECDSASigner",
    "get_signer",
    "sign_data",
    "verify_signature",
    # Manager
    "LicenseManager",
    "get_license_manager",
    "reset_license_manager",
]
