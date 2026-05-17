"""
ZENIC-AGENTS - ActionExecutor System (Phase 3)

Facade module that re-exports all public symbols from the executors sub-package.
All implementation has been modularized into src/core/executors/.
Phase 3 adds: Safety Gate, Audit Logger, Blueprint Schema, DiscordExecutor,
and DAG integration via ActionDispatcher.
"""

from .executors import (
    # Base
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
    # Executors
    EmailExecutor,
    DatabaseExecutor,
    FileExecutor,
    TransformExecutor,
    ScheduleExecutor,
    # Safety Gate
    SafetyGate,
    SafetyVerdict,
    SafetyCheckResult,
    ActionCategory,
    SafetyRule,
    ActionRateLimiter,
    get_default_safety_gate,
    reset_safety_gate,
    # Audit Logger
    ExecutorAuditLogger,
    AuditEntry,
    AuditQuery,
    AuditMerkleChain,
    AuditPersistence,
    get_default_audit_logger,
    reset_audit_logger,
    # Blueprint Schema
    Blueprint,
    BlueprintMetadata,
    BlueprintValidator,
    BlueprintLoader,
    ExecutorSchema,
    BusinessRule,
    ActionTemplate,
    get_default_blueprint,
    # Dispatch Action
    ActionDispatcher,
    DispatchRequest,
    DispatchResult,
    exec_dispatch_action,
    get_default_dispatcher,
    reset_dispatcher,
    # Email Parts
    EmailTemplateEngine,
    EmailTemplate,
    EmailRateLimiter,
    # Database Parts
    SQLCipherAdapter,
    CRUDValidator,
    TransactionManager,
    Transaction,
)

# Notification Parts — imported from channels package
from .channels import ChannelRouter, ChannelPriority

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
    # Executors
    "EmailExecutor",
    "DatabaseExecutor",
    "FileExecutor",
    "TransformExecutor",
    "ScheduleExecutor",
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
    # Email Parts
    "EmailTemplateEngine",
    "EmailTemplate",
    "EmailRateLimiter",
    # Database Parts
    "SQLCipherAdapter",
    "CRUDValidator",
    "TransactionManager",
    "Transaction",
    # Notification Parts (from channels)
    "ChannelRouter",
    "ChannelPriority",
]
