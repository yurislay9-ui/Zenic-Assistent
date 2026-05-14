"""
Zenic-Agents Asistente - Blueprint Types

Core type definitions for the certified Blueprint system.
All dataclasses, enums, and value objects used across
the Blueprints subsystem.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────

class BlueprintStatus(str, Enum):
    """Lifecycle status of a Blueprint."""
    DRAFT = "draft"               # Under development
    CERTIFIED = "certified"       # ECDSA-signed, production-ready
    DEPRECATED = "deprecated"     # Superseded by newer version
    REVOKED = "revoked"           # Certificate revoked


class BlueprintTier(str, Enum):
    """Availability tier for a Blueprint."""
    FREE = "free"                 # Available to all users
    PRO = "pro"                   # Pro plan required
    ENTERPRISE = "enterprise"     # Enterprise plan required
    PARTNER = "partner"           # Partner-created (revenue share)


class FieldType(str, Enum):
    """Database field types for Blueprint DB schema."""
    UUID = "uuid"
    TEXT = "text"
    STR = "str"
    INT = "int"
    FLOAT = "float"
    DECIMAL = "decimal"
    BOOL = "bool"
    DATE = "date"
    DATETIME = "datetime"
    JSON = "json"
    BLOB = "blob"


class ConflictStrategy(str, Enum):
    """Strategy for resolving Blueprint composition conflicts."""
    LAST_WINS = "last_wins"       # Later Blueprint overrides
    FIRST_WINS = "first_wins"     # First Blueprint keeps priority
    MERGE = "merge"               # Merge both (lists concatenated, dicts merged)
    FAIL = "fail"                 # Raise error on conflict


class OnboardingStepType(str, Enum):
    """Types of onboarding steps."""
    SELECT_BLUEPRINT = "select_blueprint"
    IMPORT_DATA = "import_data"
    CONFIGURE_MONITORS = "configure_monitors"
    CONFIGURE_NOTIFICATIONS = "configure_notifications"
    REVIEW = "review"
    COMPLETE = "complete"


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class DBFieldSchema:
    """Schema for a single database field."""
    name: str
    field_type: FieldType = FieldType.STR
    required: bool = True
    unique: bool = False
    indexed: bool = False
    default: Any = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class DBEntitySchema:
    """Schema for a database entity/table."""
    name: str
    fields: List[DBFieldSchema] = field(default_factory=list)
    primary_key: str = "id"
    indexes: List[Dict[str, Any]] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class DBSchema:
    """Complete database schema for a Blueprint."""
    entities: List[DBEntitySchema] = field(default_factory=list)
    migrations: List[Dict[str, Any]] = field(default_factory=list)
    version: str = "1.0.0"


@dataclass
class MonitorHook:
    """SNA monitor configuration embedded in a Blueprint."""
    monitor_id: str
    weight: str = "lightweight"           # lightweight, medium, heavy
    interval_seconds: float = 300.0
    enabled: bool = True
    thresholds: List[Dict[str, Any]] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    notification_channel: str = "log"


@dataclass
class BusinessRuleDef:
    """Business rule definition within a Blueprint."""
    rule_id: str
    name: str
    description: str = ""
    executor_type: str = ""
    condition: str = ""
    action: str = ""
    severity: str = "warning"
    active: bool = True


@dataclass
class ActionTemplateDef:
    """Predefined action template in a Blueprint."""
    template_id: str
    name: str
    description: str = ""
    executor_type: str = ""
    config_template: Dict[str, Any] = field(default_factory=dict)
    safety_category: str = "moderate"
    requires_confirmation: bool = False
    requires_approval: bool = False


@dataclass
class BlueprintSignature:
    """ECDSA cryptographic signature for Blueprint certification."""
    algorithm: str = "ECDSA-P256"
    signature_hex: str = ""
    public_key_hex: str = ""
    signed_at: float = 0.0
    signer_id: str = ""
    certificate_id: str = ""

    def __post_init__(self) -> None:
        if not self.certificate_id:
            self.certificate_id = uuid.uuid4().hex[:16]


@dataclass
class BlueprintCompatibility:
    """Compatibility information between Blueprints."""
    blueprint_name: str
    version_range: str = "*"           # Semver range, e.g., ">=1.0.0,<3.0.0"
    composition_notes: str = ""
    known_conflicts: List[str] = field(default_factory=list)


@dataclass
class BlueprintMetadataV2:
    """Enhanced metadata for certified Blueprints."""
    name: str
    version: str = "1.0.0"
    domain: str = ""
    subdomain: str = ""
    description: str = ""
    author: str = ""
    tier: BlueprintTier = BlueprintTier.FREE
    status: BlueprintStatus = BlueprintStatus.DRAFT
    signature: Optional[BlueprintSignature] = None
    compatibility: List[BlueprintCompatibility] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    icon: str = ""
    scale: str = "medium"              # small, medium, large, enterprise
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at


@dataclass
class OnboardingStep:
    """A single step in the Blueprint onboarding flow."""
    step_type: OnboardingStepType
    title: str = ""
    description: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    required: bool = True
    completed: bool = False


@dataclass
class OnboardingSession:
    """An active onboarding session."""
    session_id: str = ""
    blueprint_names: List[str] = field(default_factory=list)
    steps: List[OnboardingStep] = field(default_factory=list)
    current_step: int = 0
    tenant_id: str = ""
    user_id: str = ""
    import_data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    completed_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = time.time()

    @property
    def is_complete(self) -> bool:
        """Check if all required steps are completed."""
        return all(
            step.completed or not step.required
            for step in self.steps
        )


@dataclass
class PartnerInfo:
    """Partner information for revenue-shared Blueprints."""
    partner_id: str
    partner_name: str
    revenue_share_pct: float = 0.0     # 0-100
    api_key_prefix: str = ""
    certified: bool = False
    created_at: float = 0.0


@dataclass
class BlueprintStats:
    """Statistics for a Blueprint."""
    installations: int = 0
    active_users: int = 0
    alerts_triggered: int = 0
    actions_executed: int = 0
    revenue_cents: int = 0             # Revenue in cents
