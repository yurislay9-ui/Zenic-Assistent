"""
ZENIC-AGENTS — Event-driven Actions Engine (B1)

Package providing the core event-driven automation components:

  - TriggerMap: Declarative mapping from event patterns to automations
  - EventSchemaRegistry: Event payload validation against declared schemas
  - ReplayQueue: Dead-letter queue with event replay capability

Removed (external API connections deleted):
  - WebhookIngestionEngine: Was inbound webhook handler with HMAC verification

Each component is thread-safe and follows the singleton pattern
for production use. All SQLite-persisted components store data
under ~/.zenic_agents/db/ by default.
"""

# ── TriggerMap ──
from .trigger_map import (
    TriggerMap,
    TriggerMapping,
    TriggerCondition,
    ConditionOperator,
    get_trigger_map,
    reset_trigger_map,
)

# ── EventSchemaRegistry ──
from .schema_registry import (
    EventSchemaRegistry,
    EventSchema,
    ValidationResult,
    ValidationIssue,
    IssueType,
    get_schema_registry,
    reset_schema_registry,
)

# ── ReplayQueue ──
from .replay_queue import (
    ReplayQueue,
    DeadLetterEvent,
    DeadLetterStatus,
    RetryResult,
    BatchRetryResult,
    get_replay_queue,
    reset_replay_queue,
)

__all__ = [
    # TriggerMap
    "TriggerMap",
    "TriggerMapping",
    "TriggerCondition",
    "ConditionOperator",
    "get_trigger_map",
    "reset_trigger_map",
    # EventSchemaRegistry
    "EventSchemaRegistry",
    "EventSchema",
    "ValidationResult",
    "ValidationIssue",
    "IssueType",
    "get_schema_registry",
    "reset_schema_registry",
    # ReplayQueue
    "ReplayQueue",
    "DeadLetterEvent",
    "DeadLetterStatus",
    "RetryResult",
    "BatchRetryResult",
    "get_replay_queue",
    "reset_replay_queue",
]
