"""
Phase 6 imports: Approval, Defense, License, DegradedMode, Integration.

Split from src/core/__init__.py for maintainability.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Phase 6: Approval System ──────────────────────────────
try:
    from src.core.approval import (
        ApprovalChain,
        ApprovalRequest,
        ApprovalResult,
        ApprovalStatus,
        ApprovalPriority,
        WorkflowEngine,
        WorkflowDefinition,
        WorkflowStep,
        get_approval_chain,
        get_workflow_engine,
    )
except ImportError as exc:
    logger.warning("core: Approval import failed: %s", exc)
    ApprovalChain = None  # type: ignore[misc,assignment]
    ApprovalRequest = None  # type: ignore[misc,assignment]
    ApprovalResult = None  # type: ignore[misc,assignment]
    ApprovalStatus = None  # type: ignore[misc,assignment]
    ApprovalPriority = None  # type: ignore[misc,assignment]
    WorkflowEngine = None  # type: ignore[misc,assignment]
    WorkflowDefinition = None  # type: ignore[misc,assignment]
    WorkflowStep = None  # type: ignore[misc,assignment]
    get_approval_chain = None  # type: ignore[misc,assignment]
    get_workflow_engine = None  # type: ignore[misc,assignment]

# ── Phase 6: Defense in Depth ────────────────────────────
try:
    from src.core.defense import (
        AntiTamperingLayer,
        TamperSeverity,
        BinaryHardeningLayer,
        HardeningLevel,
        EncryptionManager,
        EncryptionLevel,
        IntegrityVerifier,
        IntegrityStatus,
        ServerSecretsLayer,
        SecretType,
        DefenseManager,
        get_defense_manager,
    )
except ImportError as exc:
    logger.warning("core: Defense import failed: %s", exc)
    AntiTamperingLayer = None  # type: ignore[misc,assignment]
    TamperSeverity = None  # type: ignore[misc,assignment]
    BinaryHardeningLayer = None  # type: ignore[misc,assignment]
    HardeningLevel = None  # type: ignore[misc,assignment]
    EncryptionManager = None  # type: ignore[misc,assignment]
    EncryptionLevel = None  # type: ignore[misc,assignment]
    IntegrityVerifier = None  # type: ignore[misc,assignment]
    IntegrityStatus = None  # type: ignore[misc,assignment]
    ServerSecretsLayer = None  # type: ignore[misc,assignment]
    SecretType = None  # type: ignore[misc,assignment]
    DefenseManager = None  # type: ignore[misc,assignment]
    get_defense_manager = None  # type: ignore[misc,assignment]

# ── Phase 6: Cryptographic Licensing ─────────────────────
try:
    from src.core.license import (
        LicenseManager,
        LicenseTier,
        LicenseStatus,
        LicenseInfo,
        LicenseVerificationResult,
        KillSwitchStatus,
        HardwareBindingStrength,
        get_license_manager,
    )
except ImportError as exc:
    logger.warning("core: License import failed: %s", exc)
    LicenseManager = None  # type: ignore[misc,assignment]
    LicenseTier = None  # type: ignore[misc,assignment]
    LicenseStatus = None  # type: ignore[misc,assignment]
    LicenseInfo = None  # type: ignore[misc,assignment]
    LicenseVerificationResult = None  # type: ignore[misc,assignment]
    KillSwitchStatus = None  # type: ignore[misc,assignment]
    HardwareBindingStrength = None  # type: ignore[misc,assignment]
    get_license_manager = None  # type: ignore[misc,assignment]

# ── Phase 6: Degraded Mode / Paralysis ───────────────────
try:
    from src.core.degraded_mode import (
        DegradedModeManager,
        SystemMode,
        ModeCapabilities,
        ModeTransition,
        get_degraded_mode_manager,
    )
except ImportError as exc:
    logger.warning("core: DegradedMode import failed: %s", exc)
    DegradedModeManager = None  # type: ignore[misc,assignment]
    SystemMode = None  # type: ignore[misc,assignment]
    ModeCapabilities = None  # type: ignore[misc,assignment]
    ModeTransition = None  # type: ignore[misc,assignment]
    get_degraded_mode_manager = None  # type: ignore[misc,assignment]

# ── Phase 6: Integration ─────────────────────────────────
try:
    from src.core.phase6_init import initialize_phase6, get_phase6_status
except ImportError as exc:
    logger.warning("core: phase6_init import failed: %s", exc)
    initialize_phase6 = None  # type: ignore[misc,assignment]
    get_phase6_status = None  # type: ignore[misc,assignment]
