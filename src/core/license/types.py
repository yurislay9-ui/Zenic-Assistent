"""
Zenic-Agents Asistente - License Types (Phase 6.3)

Data types for the cryptographic licensing system.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LicenseTier(str, Enum):
    """License tier levels — aligned with zenic-subscription Rust crate.

    5-tier model:
    - STARTER: $29/mo USDT TRC20 — basic pipeline
    - BUSINESS: $99/mo USDT TRC20 — full pipeline (14-day trial tier)
    - ENTERPRISE: $299/mo USDT TRC20 — unlimited features
    - ON_PREMISE_ENTERPRISE: $799/mo + $2,000 setup USDT TRC20 — self-hosted
    - TRIAL: 14-day free trial with Business plan access
    """
    STARTER = "starter"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"
    ON_PREMISE_ENTERPRISE = "on_premise_enterprise"
    TRIAL = "trial"


class LicenseStatus(str, Enum):
    """Status of a license."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    GRACE_PERIOD = "grace_period"
    TRIAL = "trial"
    INVALID = "invalid"
    PENDING_ACTIVATION = "pending_activation"


class HardwareBindingStrength(str, Enum):
    """Strength of hardware binding."""
    NONE = "none"
    SOFT = "soft"       # Allows minor hardware changes
    STRICT = "strict"   # Exact hardware match required


@dataclass
class LicenseInfo:
    """Full license information.

    Attributes:
        license_id: Unique license identifier.
        tier: License tier.
        status: Current license status.
        issued_to: License holder name or organization.
        issued_at: Unix timestamp when issued.
        expires_at: Unix timestamp when license expires (0 = perpetual).
        features: List of features enabled by this license.
        max_users: Maximum concurrent users.
        hardware_id: Hardware fingerprint bound to this license.
        binding_strength: How strict hardware binding is.
        signature: ECDSA signature of the license data.
        metadata: Additional license metadata.
    """
    license_id: str = ""
    tier: LicenseTier = LicenseTier.FREE
    status: LicenseStatus = LicenseStatus.INVALID
    issued_to: str = ""
    issued_at: float = 0.0
    expires_at: float = 0.0
    features: List[str] = field(default_factory=list)
    max_users: int = 1
    hardware_id: str = ""
    binding_strength: HardwareBindingStrength = HardwareBindingStrength.SOFT
    signature: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if the license has expired."""
        if self.expires_at == 0:
            return False  # Perpetual license
        return time.time() > self.expires_at

    def is_perpetual(self) -> bool:
        """Check if this is a perpetual (non-expiring) license."""
        return self.expires_at == 0

    def days_remaining(self) -> Optional[int]:
        """Get days remaining until expiration. None if perpetual."""
        if self.is_perpetual():
            return None
        remaining = (self.expires_at - time.time()) / 86400
        return max(0, int(remaining))

    def has_feature(self, feature: str) -> bool:
        """Check if a specific feature is enabled."""
        if "all" in self.features:
            return True
        return feature in self.features

    def to_signable_data(self) -> str:
        """Create a canonical string for ECDSA signing.

        The signature covers all fields except the signature itself,
        ensuring any modification invalidates the signature.
        """
        parts = [
            self.license_id,
            self.tier.value,
            self.issued_to,
            str(self.issued_at),
            str(self.expires_at),
            ",".join(sorted(self.features)),
            str(self.max_users),
            self.hardware_id,
            self.binding_strength.value,
        ]
        return "|".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "license_id": self.license_id,
            "tier": self.tier.value,
            "status": self.status.value,
            "issued_to": self.issued_to,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "features": self.features,
            "max_users": self.max_users,
            "hardware_id": self.hardware_id,
            "binding_strength": self.binding_strength.value,
            "is_expired": self.is_expired(),
            "is_perpetual": self.is_perpetual(),
            "days_remaining": self.days_remaining(),
        }


@dataclass
class LicenseVerificationResult:
    """Result of a license verification check."""
    valid: bool
    status: LicenseStatus
    license_info: Optional[LicenseInfo] = None
    reason: str = ""
    checks_performed: List[str] = field(default_factory=list)


@dataclass
class KillSwitchStatus:
    """Status of the remote kill switch."""
    active: bool
    reason: str = ""
    activated_at: Optional[float] = None
    source: str = ""  # 'server', 'local', 'config'
