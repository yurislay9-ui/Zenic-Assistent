"""
ZENIC-AGENTS - ActionExecutor System (Phase 3)

Sistema de ejecutores de acciones reales para el AutomationEngine.
Fase 3: Integracion Safety Gate + Audit + Blueprint + remaining executors.

Executors (remaining):
  1. DatabaseExecutor   - Operaciones SQLite/SQLCipher (enhanced: CRUD validation + transactions)
  2. FileExecutor       - Operaciones de archivos con proteccion path-traversal
  3. TransformExecutor  - Transformacion y mapeo de datos
  4. ScheduleExecutor   - Programacion de jobs (APScheduler/fallback)

Removed executors (external API connections deleted):
  - EmailExecutor      - Was SMTP via aiosmtplib
  - HttpExecutor       - Was outbound HTTP via aiohttp/urllib
  - NotificationExecutor - Was multi-channel notification dispatch
  - WebhookExecutor    - Was outbound webhook + HMAC verification
  - DiscordExecutor    - Was Discord webhook messages

Infraestructura (remaining):
  - SafetyGate          - Pre-execution validation (destructive/financial/system)
  - ExecutorAuditLogger - Audit logging with Merkle chain integrity
  - BlueprintSchema     - Blueprint parameterization for executors
  - ActionDispatcher    - DAG -> Executor pipeline integration
  - SQLCipherAdapter    - Encrypted database connections (AES-256)
  - CRUDValidator       - CRUD operation validation with Blueprint schema
  - TransactionManager  - Transaction management with rollback support

Removed infrastructure (external connections deleted):
  - ChannelRouter       - Was multi-channel notification routing
  - EmailTemplateEngine - Was email template rendering

Todos los ejecutores:
  - Manejan errores gracefulmente (nunca raise, siempre devuelven ActionResult)
  - Tienen modo dry-run/fallback cuando faltan dependencias
  - Son testeable sin servicios externos
  - Usan logging extensivo
  - Pasan por Safety Gate antes de ejecutar (si esta habilitado)
  - Son auditados despues de ejecutar (si esta habilitado)
"""

# ── Base ──
from .base import (
    ActionResult,
    ActionExecutor,
    ExecutorRegistry,
    _validate_email,
    _validate_url,
    _safe_path,
    _validate_sql,
    _HAS_AIOSMTPLIB,
    _HAS_AIOHTTP,
    _HAS_APSCHEDULER,
    get_default_registry,
    reset_default_registry,
)

# ── Executors (remaining) ──
from .database_executor import DatabaseExecutor
from .file_executor import FileExecutor
from .transform_executor import TransformExecutor
from .schedule_executor import ScheduleExecutor

# ── Executors (Phase 2 — channel integration) ──
from .email_executor import EmailExecutor
from .jira_executor import JiraExecutor
from .servicenow_executor import ServiceNowExecutor

# ── Safety Gate ──
from .safety_gate import (
    SafetyGate,
    SafetyVerdict,
    SafetyCheckResult,
    ActionCategory,
    SafetyRule,
    ActionRateLimiter,
    get_default_safety_gate,
    reset_safety_gate,
)

# ── Audit Logger ──
from .audit_logger import (
    ExecutorAuditLogger,
    AuditEntry,
    AuditQuery,
    AuditMerkleChain,
    AuditPersistence,
    get_default_audit_logger,
    reset_audit_logger,
)

# ── Blueprint Schema ──
from .blueprint_schema import (
    Blueprint,
    BlueprintMetadata,
    BlueprintValidator,
    BlueprintLoader,
    ExecutorSchema,
    BusinessRule,
    ActionTemplate,
    get_default_blueprint,
)

# ── Dispatch Action (DAG Integration) ──
from .dispatch_action import (
    ActionDispatcher,
    DispatchRequest,
    DispatchResult,
    exec_dispatch_action,
    get_default_dispatcher,
    reset_dispatcher,
)

# ── Email Parts (Phase 2) ──
from .email_parts import (
    EmailTemplateEngine,
    EmailTemplate,
    EmailRateLimiter,
    OAuth2TokenManager,
    OAuth2Config,
    OAuth2Token,
    GraphAPIEmailProvider,
)

# ── Database Parts ──
from .db_parts import SQLCipherAdapter, CRUDValidator, TransactionManager, Transaction

# Phase A: Impact Preview + Policy Engine
from .impact_preview import (
    ImpactPreviewEngine,
    ImpactPreview,
    DBImpactPreview,
    FileImpactPreview,
    EmailImpactPreview,
    ImpactField,
    ImpactRiskLevel,
    get_impact_preview_engine,
    reset_impact_preview_engine,
)
from .policy_engine import (
    PolicyEngine,
    PolicyRule,
    PolicyDecision,
    PolicyCondition,
    PolicyAction,
    ConditionOperator,
    get_policy_engine,
    reset_policy_engine,
)
# Phase A: DB Journal + Coordinated Rollback
from .db_journal import (
    DBTransactionJournal,
    JournalEntry,
    RollbackResult as JournalRollbackResult,
    get_db_journal,
    reset_db_journal,
)
from .coordinated_rollback import (
    CoordinatedRollbackManager,
    CoordinatedAction,
    ResourceRecord,
    ResourceType,
    ActionStatus as CoordinatedActionStatus,
    CoordinatedRollbackResult,
    get_coordinated_rollback_manager,
    reset_coordinated_rollback_manager,
)

# Phase C1: Dry-Run / Simulation Engine
from .dry_run_executor import (
    DryRunOperation,
    DryRunResult,
    DryRunExecutor,
    dry_run_dispatch,
    get_dry_run_executor,
    reset_dry_run_executor,
)
from .simulation_engine import (
    SimulationResult,
    ScenarioComparison,
    SimulationEngine,
    get_simulation_engine,
    reset_simulation_engine,
)
from .diff_preview import (
    DiffEntry,
    DiffResult,
    DiffPreviewEngine,
    get_diff_preview_engine,
    reset_diff_preview_engine,
)

__all__ = [
    # Base
    "ActionResult",
    "ActionExecutor",
    "ExecutorRegistry",
    "_validate_email",
    "_validate_url",
    "_safe_path",
    "_validate_sql",
    "_HAS_AIOSMTPLIB",
    "_HAS_AIOHTTP",
    "_HAS_APSCHEDULER",
    "get_default_registry",
    "reset_default_registry",
    # Executors (7)
    "DatabaseExecutor",
    "FileExecutor",
    "TransformExecutor",
    "ScheduleExecutor",
    # Executors (Phase 2)
    "EmailExecutor",
    "ServiceNowExecutor",
    "JiraExecutor",
    # Email Parts (Phase 2)
    "EmailTemplateEngine",
    "EmailTemplate",
    "EmailRateLimiter",
    "OAuth2TokenManager",
    "OAuth2Config",
    "OAuth2Token",
    "GraphAPIEmailProvider",
    # Safety Gate
    "SafetyGate",
    "SafetyVerdict",
    "SafetyCheckResult",
    "ActionCategory",
    "SafetyRule",
    "ActionRateLimiter",
    "get_default_safety_gate",
    "reset_safety_gate",
    # Audit Logger
    "ExecutorAuditLogger",
    "AuditEntry",
    "AuditQuery",
    "AuditMerkleChain",
    "AuditPersistence",
    "get_default_audit_logger",
    "reset_audit_logger",
    # Blueprint Schema
    "Blueprint",
    "BlueprintMetadata",
    "BlueprintValidator",
    "BlueprintLoader",
    "ExecutorSchema",
    "BusinessRule",
    "ActionTemplate",
    "get_default_blueprint",
    # Dispatch Action
    "ActionDispatcher",
    "DispatchRequest",
    "DispatchResult",
    "exec_dispatch_action",
    "get_default_dispatcher",
    "reset_dispatcher",
    # Database Parts
    "SQLCipherAdapter",
    "CRUDValidator",
    "TransactionManager",
    "Transaction",
    # Phase A: Impact Preview
    "ImpactPreviewEngine",
    "ImpactPreview",
    "DBImpactPreview",
    "FileImpactPreview",
    "EmailImpactPreview",
    "ImpactField",
    "ImpactRiskLevel",
    "get_impact_preview_engine",
    "reset_impact_preview_engine",
    # Phase A: Policy Engine
    "PolicyEngine",
    "PolicyRule",
    "PolicyDecision",
    "PolicyCondition",
    "PolicyAction",
    "ConditionOperator",
    "get_policy_engine",
    "reset_policy_engine",
    # Phase A: DB Journal
    "DBTransactionJournal",
    "JournalEntry",
    "JournalRollbackResult",
    "get_db_journal",
    "reset_db_journal",
    # Phase A: Coordinated Rollback
    "CoordinatedRollbackManager",
    "CoordinatedAction",
    "ResourceRecord",
    "ResourceType",
    "CoordinatedActionStatus",
    "CoordinatedRollbackResult",
    "get_coordinated_rollback_manager",
    "reset_coordinated_rollback_manager",
    # Phase C1: Dry-Run / Simulation Engine
    "DryRunOperation",
    "DryRunResult",
    "DryRunExecutor",
    "dry_run_dispatch",
    "get_dry_run_executor",
    "reset_dry_run_executor",
    "SimulationResult",
    "ScenarioComparison",
    "SimulationEngine",
    "get_simulation_engine",
    "reset_simulation_engine",
    "DiffEntry",
    "DiffResult",
    "DiffPreviewEngine",
    "get_diff_preview_engine",
    "reset_diff_preview_engine",
]
